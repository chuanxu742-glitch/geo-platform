"""Explicit, bounded single-page observations; never rankings or publication proof."""
import fnmatch
import hashlib
import http.client
import ipaddress
import json
import os
import queue
import re
import socket
import ssl
import threading
import time
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator

from .common import require, rows, serialize
from .db import get_db
from . import models
from .schemas import Payload

router = APIRouter()
MAX_BYTES = 2 * 1024 * 1024
ROBOTS_MAX_BYTES = 256 * 1024
MAX_REDIRECTS = 5
FETCH_TIMEOUT = 15.0
SOCKET_TIMEOUT = 5.0
AGENTS = {"OAI-SearchBot": "search", "GPTBot": "training", "Googlebot": "search"}
SAFE_HEADERS = {"content-type", "content-length", "last-modified", "etag", "x-robots-tag"}


class FetchError(Exception):
    def __init__(self, code, *, final_url="", http_status=None, headers=None, redirects=None):
        # Codes are local constants, never upstream exception messages or bodies.
        super().__init__(code)
        self.code = code
        self.final_url = final_url
        self.http_status = http_status
        self.headers = headers or {}
        self.redirects = redirects or []


def validate_url(url: str) -> str:
    try:
        if not isinstance(url, str) or re.search(r"[\x00-\x20\x7f\\]", url):
            raise ValueError
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if "%" in host or not re.fullmatch(r"[a-z0-9.:-]+", host):
            raise ValueError
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
        scheme = parsed.scheme.lower()
        authority = f"[{host}]" if ":" in host else host
        if port is not None and port != (443 if scheme == "https" else 80):
            authority += f":{port}"
        return urlunsplit((scheme, authority, quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~"), quote(parsed.query, safe="%/:?@!$&'()*+,;=-._~"), ""))
    except (ValueError, UnicodeError):
        raise HTTPException(422, "URL必须为不含凭据的有效HTTP(S)地址") from None


def _origin(url):
    parsed = urlsplit(url)
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


def _allowed(host, port):
    # No suffix/wildcard match. A host-only entry permits only standard HTTP(S) ports.
    authority = f"[{host}]" if ":" in host else host
    entries = {part.strip().lower() for part in os.getenv("GEO_HTTP_ALLOWLIST", "").split(",") if part.strip()}
    return f"{authority}:{port}" in entries or (port in (80, 443) and authority in entries)


def _public_ip(address):
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv6Address):
        # Translation/tunnel prefixes can conceal an otherwise blocked IPv4 peer.
        if ip in ipaddress.ip_network("64:ff9b::/96") or ip.sixtofour is not None or ip.teredo is not None:
            return False
    # Also reject shared, reserved, unspecified and multicast space.
    return ip.is_global and not ip.is_multicast and not ip.is_reserved and not ip.is_loopback and not ip.is_link_local


def _resolve(host, port, deadline):
    result = queue.Queue(maxsize=1)

    def lookup():
        try:
            result.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except OSError:
            result.put(None)

    # A stalled system resolver must not hold the HTTP request open indefinitely.
    threading.Thread(target=lookup, daemon=True).start()
    try:
        addresses = result.get(timeout=max(0.001, deadline - time.monotonic()))
    except queue.Empty:
        raise FetchError("dns_timeout") from None
    if not addresses:
        raise FetchError("dns_failed")
    if not _allowed(host, port):
        try:
            if any(not _public_ip(item[4][0]) for item in addresses):
                raise FetchError("destination_not_public")
        except ValueError:
            raise FetchError("invalid_dns_address") from None
    return addresses[0]


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, secure, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address = address
        self.secure = secure
        self.transport_sock = None

    def connect(self):
        family, socktype, protocol, _, sockaddr = self.address
        self.sock = socket.socket(family, socktype, protocol)
        self.sock.settimeout(self.timeout)
        self.sock.connect(sockaddr)  # Numeric sockaddr only: no second DNS lookup.
        if self.secure:
            self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)
        self.transport_sock = self.sock


def _request(url, address, deadline, max_bytes, *, method="GET", body=None, request_headers=None, accept_errors=False):
    parsed = urlsplit(url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchError("fetch_timeout")
    connection = _PinnedConnection(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), address, parsed.scheme == "https", min(SOCKET_TIMEOUT, remaining))

    def interrupt():
        sock = connection.transport_sock or connection.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()

    timer = threading.Timer(remaining, interrupt)
    timer.daemon = True
    timer.start()
    status = None
    headers = {}
    try:
        outgoing = {"user-agent": "GEO-PageObserver/1.0", "accept": "text/html,text/plain;q=0.9,*/*;q=0.1"}
        outgoing.update({key.lower(): value for key, value in (request_headers or {}).items() if key.lower() not in {"host", "content-length", "transfer-encoding", "accept-encoding", "connection"}})
        outgoing.update({"host": parsed.netloc, "accept-encoding": "identity", "connection": "close"})
        connection.request(method, urlunsplit(("", "", parsed.path or "/", parsed.query, "")), body=body, headers=outgoing)
        response = connection.getresponse()
        status = response.status
        headers = {key.lower(): value for key, value in response.getheaders() if key.lower() in SAFE_HEADERS}
        location = response.getheader("Location")
        if status in (301, 302, 303, 307, 308):
            return status, headers, location, b""
        if not accept_errors and not 200 <= status < 300:
            raise FetchError("http_status_failure")
        if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
            raise FetchError("unsupported_content_encoding")
        length = response.getheader("Content-Length")
        if length is not None:
            try:
                if int(length) < 0 or int(length) > max_bytes:
                    raise FetchError("response_too_large")
            except ValueError:
                raise FetchError("invalid_content_length") from None
        chunks = []
        size = 0
        while True:
            if time.monotonic() >= deadline:
                raise FetchError("fetch_timeout")
            chunk = response.read1(min(65536, max_bytes + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise FetchError("response_too_large")
            chunks.append(chunk)
        if time.monotonic() >= deadline:
            raise FetchError("fetch_timeout")
        if length is not None and size != int(length):
            raise FetchError("incomplete_response")
        return status, headers, location, b"".join(chunks)
    except FetchError as exc:
        exc.http_status = status
        exc.headers = headers
        raise
    except (OSError, http.client.HTTPException, ValueError):
        raise FetchError("fetch_timeout" if time.monotonic() >= deadline else "transport_failure", http_status=status, headers=headers) from None
    finally:
        timer.cancel()
        connection.close()


def _response_view(url, status, headers, redirects, raw):
    charset = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", headers.get("content-type", ""), re.I)
    try:
        text = raw.decode(charset.group(1) if charset else "utf-8", errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    return {"final_url": url, "http_status": status, "html": text, "headers": headers, "redirects": redirects, "bytes": len(raw), "response_sha256": hashlib.sha256(raw).hexdigest()}


def _fetch(url, max_bytes, same_origin=False):
    current = ""
    redirects = []
    deadline = time.monotonic() + FETCH_TIMEOUT
    try:
        current = validate_url(url)
        initial_origin = _origin(current)
        for hop in range(MAX_REDIRECTS + 1):
            parsed = urlsplit(current)
            address = _resolve(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), deadline)
            status, headers, location, raw = _request(current, address, deadline, max_bytes)
            if status in (301, 302, 303, 307, 308):
                if not location:
                    raise FetchError("redirect_without_location", http_status=status, headers=headers)
                if hop == MAX_REDIRECTS:
                    raise FetchError("too_many_redirects", http_status=status, headers=headers)
                target = validate_url(urljoin(current, location))
                redirects.append({"url": current, "status": status, "location": target})
                if same_origin and _origin(target) != initial_origin:
                    raise FetchError("cross_origin_robots_redirect", http_status=status, headers=headers)
                current = target
                continue
            return _response_view(current, status, headers, redirects, raw)
    except HTTPException:
        raise FetchError("invalid_url", final_url=current, redirects=redirects) from None
    except FetchError as exc:
        exc.final_url = current
        exc.redirects = redirects
        raise


def fetch_url(url: str) -> dict:
    return _fetch(url, MAX_BYTES)


def controlled_local_url(url: str) -> bool:
    """Whether an explicit literal-loopback admin exception permits local HTTP."""
    try:
        parsed = urlsplit(validate_url(url))
        return ipaddress.ip_address(parsed.hostname).is_loopback and _allowed(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except (HTTPException, ValueError):
        return False


def request_url(url: str, *, method: str = "GET", body: bytes | None = None, headers: dict | None = None) -> dict:
    """One pinned request, no redirects/retries; credentials never cross origins.

    Caller owns authorization and HTTPS policy. Non-2xx responses remain explicit
    results so an authenticated publisher can distinguish rejection from timeout.
    """
    if method not in {"GET", "POST"}:
        raise FetchError("unsupported_method")
    if body is not None and (not isinstance(body, bytes) or len(body) > MAX_BYTES):
        raise FetchError("request_body_invalid_or_too_large")
    current = ""
    deadline = time.monotonic() + FETCH_TIMEOUT
    try:
        current = validate_url(url)
        parsed = urlsplit(current)
        address = _resolve(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), deadline)
        status, response_headers, _, raw = _request(current, address, deadline, MAX_BYTES, method=method, body=body, request_headers=headers, accept_errors=True)
        return _response_view(current, status, response_headers, [], raw)
    except HTTPException:
        raise FetchError("invalid_url", final_url=current) from None
    except FetchError as exc:
        exc.final_url = current
        raise


class _PageParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    HIDDEN = {"head", "title", "script", "style", "template", "noscript", "iframe", "object"}
    BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "nav", "aside", "li", "ul", "ol", "table", "tr", "td", "th", "blockquote", "pre", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.visible = []
        self.title_parts = []
        self.headings = []
        self.meta_description = ""
        self.canonical = ""
        self.canonical_links = []
        self.hreflang_links = []
        self.base_href = ""
        self.robots_meta = []
        self.json_ld = []
        self.json_errors = []
        self.node_count = 0

    def handle_starttag(self, tag, attrs):
        self.node_count += 1
        if len(self.stack) >= 256 or self.node_count > 100000:
            raise FetchError("html_complexity_limit")
        attrs = dict(attrs)
        location = f"line {self.getpos()[0]}, column {self.getpos()[1] + 1}: <{tag}>"
        inherited = bool(self.stack and self.stack[-1]["hidden"])
        style = re.sub(r"\s+", "", attrs.get("style") or "").lower()
        hidden = inherited or tag in self.HIDDEN or "hidden" in attrs or (attrs.get("aria-hidden") or "").lower() == "true" or bool(re.search(r"(?:^|;)(?:display:none|visibility:(?:hidden|collapse))(?:!important)?(?:;|$)", style)) or (tag == "input" and attrs.get("type", "").lower() == "hidden")
        node = {"tag": tag, "hidden": hidden, "text": [], "location": location, "json": tag == "script" and (attrs.get("type") or "").split(";", 1)[0].strip().lower() == "application/ld+json"}
        # Metadata is observable even though head content is never visible text.
        if tag == "meta":
            name = (attrs.get("name") or "").lower()
            content = attrs.get("content") or ""
            if name == "description" and not self.meta_description:
                self.meta_description = content.strip()
            if name in {"robots", "googlebot", "oai-searchbot", "gptbot"}:
                self.robots_meta.append({"name": name, "content": content, "location": location})
        if tag == "base" and not self.base_href:
            self.base_href = attrs.get("href") or ""
        if tag == "link":
            rel = (attrs.get("rel") or "").lower().split()
            if "canonical" in rel:
                self.canonical_links.append({"href": attrs.get("href") or "", "location": location})
                if not self.canonical:
                    self.canonical = attrs.get("href") or ""
            if "alternate" in rel and attrs.get("hreflang"):
                self.hreflang_links.append({"language": attrs["hreflang"], "href": attrs.get("href") or "", "location": location})
        if tag in self.BLOCK and not hidden:
            self.visible.append("\n")
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if not self.stack or not self.stack[-1]["hidden"]:
            self.visible.append(data)
        for node in self.stack:
            if node["tag"] == "title" or node["json"] or (node["tag"] in {"h1", "h2", "h3", "h4", "h5", "h6"} and not self.stack[-1]["hidden"]):
                node["text"].append(data)

    def _finish(self, node):
        text = "".join(node["text"])
        if node["tag"] == "title":
            self.title_parts.append(text)
        elif node["tag"] in {"h1", "h2", "h3", "h4", "h5", "h6"} and not node["hidden"]:
            self.headings.append({"level": int(node["tag"][1]), "text": " ".join(text.split()), "location": node["location"]})
        elif node["json"]:
            try:
                value = json.loads(text, parse_constant=self._reject_constant)
                pending = [(value, 0)]
                while pending:
                    item, depth = pending.pop()
                    if depth > 64:
                        raise FetchError("json_ld_complexity_limit")
                    if isinstance(item, (dict, list)):
                        children = item.values() if isinstance(item, dict) else item
                        pending.extend((child, depth + 1) for child in children)
                self.json_ld.append(value)
            except RecursionError:
                raise FetchError("json_ld_complexity_limit") from None
            except ValueError:
                self.json_errors.append(node["location"])

    @staticmethod
    def _reject_constant(value):
        raise ValueError("Non-finite JSON number")

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i]["tag"] == tag), None)
        if index is None:
            return
        nodes = self.stack[index:]
        del self.stack[index:]
        for node in reversed(nodes):
            self._finish(node)
        if tag in self.BLOCK and not nodes[0]["hidden"]:
            self.visible.append("\n")

    def finish(self):
        self.close()
        for node in reversed(self.stack):
            self._finish(node)
        self.stack.clear()


def _robots_unknown(url, reason):
    return {"status": "unknown", "url": url, "content": "", "agents": dict.fromkeys(AGENTS), "purposes": AGENTS.copy(), "reason": reason}


def _robots_rules(content, target_url):
    groups = []
    agents, rules = [], []
    has_directive = False
    for line in content.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if has_directive:
                groups.append((agents, rules))
                agents, rules, has_directive = [], [], False
            agents.append(value.lower())
        elif agents:
            has_directive = True
            if key in ("allow", "disallow") and value:
                rules.append((key, value))
    if agents:
        groups.append((agents, rules))
    if content.strip() and not groups and any(line.split("#", 1)[0].strip() for line in content.splitlines()):
        return None
    parsed = urlsplit(target_url)
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    result = {}
    for agent in AGENTS:
        candidates = [(max((len(token) if token != "*" else 0 for token in names if token == "*" or token in agent.lower()), default=-1), entries) for names, entries in groups]
        specificity = max((score for score, _ in candidates), default=-1)
        matches = []
        for score, entries in candidates:
            if score != specificity or score < 0:
                continue
            for directive, pattern in entries:
                end = pattern.endswith("$")
                body = pattern[:-1] if end else pattern
                # fnmatch uses bounded wildcard matching rather than a chain of
                # backtracking .* expressions supplied by the remote robots file.
                glob = body.replace("[", "[[]").replace("?", "[?]") + ("" if end else "*")
                if fnmatch.fnmatchcase(target, glob):
                    matches.append((len(body.replace("*", "")), directive == "allow"))
        result[agent] = max(matches)[1] if matches else True
    return result


def _fetch_robots(final_url):
    parsed = urlsplit(final_url)
    url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try:
        fetched = _fetch(url, ROBOTS_MAX_BYTES, same_origin=True)
        content = fetched["html"]
        if "<html" in content.lower() or "<!doctype html" in content.lower():
            result = _robots_unknown(url, "non_robots_response")
        else:
            agents = _robots_rules(content, final_url)
            result = _robots_unknown(url, "unrecognized_robots") if agents is None else {"status": "success", "url": url, "content": content, "agents": agents, "purposes": AGENTS.copy()}
        result["fetch_evidence"] = {key: fetched[key] for key in ("final_url", "http_status", "redirects", "headers", "response_sha256")}
        return result
    except FetchError as exc:
        result = _robots_unknown(url, exc.code)
        result["fetch_evidence"] = {"final_url": exc.final_url, "http_status": exc.http_status, "redirects": exc.redirects, "headers": exc.headers}
        return result


def _parse_html(html):
    parser = _PageParser()
    parser.feed(html)
    parser.finish()
    return parser


def visible_text(html: str) -> str:
    """Normalize only statically visible content, never metadata or hidden text."""
    return " ".join("".join(_parse_html(html).visible).split())


def _observations(html):
    parser = _parse_html(html)
    return parser, {"html": html, "content_hash": hashlib.sha256(html.encode("utf-8")).hexdigest(), "visible_text": " ".join("".join(parser.visible).split()), "title": " ".join(" ".join(parser.title_parts).split()), "meta_description": parser.meta_description, "headings": parser.headings, "canonical": parser.canonical, "robots_meta": parser.robots_meta, "json_ld": parser.json_ld}


def _findings(snapshot, parser):
    source = {"url": snapshot.final_url or snapshot.requested_url, "source_kind": snapshot.source_kind, "content_hash": snapshot.content_hash}
    findings = []

    def add(kind, title, location, observed, recommendation, severity="warning", **context):
        findings.append(models.PageFinding(page_id=snapshot.page_id, snapshot_id=snapshot.id, kind=kind, title=title, evidence={**source, "location": location, "observed": observed, **context}, recommendation=recommendation, severity=severity))

    for kind, title, location, observed, recommendation in (
        ("missing_title", "未观察到页面标题", "document: title", snapshot.title, "在页面head内添加描述本页主题的非空title，并人工核对是否准确。"),
        ("missing_meta_description", "未观察到摘要描述", 'document: meta[name="description"]', snapshot.meta_description, "在head内填写与本页内容一致的description；此观察不保证搜索展示或AI引用。"),
        ("missing_canonical", "未观察到规范链接", 'document: link[rel~="canonical"]', snapshot.canonical, "确认是否存在重复URL；如需规范化，在head中声明预期的绝对规范URL。"),
    ):
        if not observed:
            add(kind, title, location, "absent_or_empty", recommendation)
    h1 = [item for item in snapshot.headings if item["level"] == 1]
    from .seo import technical_findings
    for finding in technical_findings(source["url"], parser):
        add(**finding)
    if not h1 or not any(item["text"] for item in h1):
        add("missing_h1", "未观察到可见的非空H1", "document: visible h1", h1, "为本页主体提供清楚且可见的一级标题。")
    for location in parser.json_errors:
        add("invalid_json_ld", "JSON-LD不是有效JSON", location, "invalid_json", "修复该script中的JSON语法后重新抓取；语法正确不等于获得排名或引用。")
    for meta in snapshot.robots_meta:
        if "noindex" in re.split(r"[\s,]+", meta["content"].lower()) or "none" in re.split(r"[\s,]+", meta["content"].lower()):
            add("noindex", "观察到索引限制指令", meta["location"], meta, "核对该指令的目标机器人与索引意图；仅在确实希望索引时调整对应指令。", "info")
    header = snapshot.fetch_evidence.get("headers", {}).get("x-robots-tag")
    if header:
        add("http_robots_directive", "观察到HTTP机器人指令", "HTTP response header: X-Robots-Tag", header, "人工核对指令作用的机器人及索引意图，不据此推断实际收录状态。", "info")
    for agent, purpose in AGENTS.items():
        add("robots_access", f"{agent} robots.txt观察", f'{snapshot.robots_txt["url"]}: User-agent {agent}', snapshot.robots_txt["agents"][agent], "此为robots访问声明而非实际抓取或收录证明；搜索与训练用途分别审阅，训练拒绝不属于页面失败。", "info", agent=agent, purpose=purpose, robots_status=snapshot.robots_txt["status"])
    return findings


def _store_snapshot(db, page, source_kind, *, fetched=None, html="", source_note="", failure=None):
    robots_url = urljoin(page.url, "/robots.txt")
    data = {"page_id": page.id, "source_kind": source_kind, "requested_url": page.url, "final_url": page.url if source_kind == "manual_import" else "", "http_status": None, "status": "success", "error": "", "content_hash": "", "html": "", "visible_text": "", "title": "", "meta_description": "", "headings": [], "canonical": "", "robots_meta": [], "json_ld": [], "robots_txt": _robots_unknown(robots_url, "manual_import_no_network" if source_kind == "manual_import" else "page_fetch_failed"), "fetch_evidence": {"redirects": [], "headers": {}, "source_kind": source_kind, "visibility_method": "static_html; excludes hidden attributes and inline styles; external CSS and JavaScript not evaluated"}}
    if source_kind == "manual_import":
        data["fetch_evidence"]["source_note"] = source_note
    if failure is not None:
        data.update(status="failure", error=failure.code, final_url=failure.final_url, http_status=failure.http_status)
        data["fetch_evidence"].update(redirects=failure.redirects, headers=failure.headers)
    elif fetched is not None:
        data.update(final_url=fetched["final_url"], http_status=fetched["http_status"])
        data["fetch_evidence"].update({key: fetched[key] for key in ("headers", "redirects", "bytes", "response_sha256")})
        data["robots_txt"] = _fetch_robots(fetched["final_url"])
        html = fetched["html"]
    parser = None
    if failure is None:
        try:
            parser, observations = _observations(html)
            data.update(observations)
            data["fetch_evidence"]["seo_metadata"] = {
                "canonical_links": parser.canonical_links,
                "hreflang_links": parser.hreflang_links,
                "base_href": parser.base_href,
            }
        except FetchError as exc:
            data.update(status="failure", error=exc.code)
    snapshot = models.PageSnapshot(**data)
    db.add(snapshot)
    db.flush()
    if parser is not None:
        db.add_all(_findings(snapshot, parser))
    db.commit()
    return snapshot


def capture_page(db, page):
    try:
        fetched = fetch_url(page.url)
        content_type = fetched["headers"].get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type and content_type not in ("text/html", "application/xhtml+xml"):
            raise FetchError("non_html_response", final_url=fetched["final_url"], http_status=fetched["http_status"], headers=fetched["headers"], redirects=fetched["redirects"])
    except FetchError as exc:
        return _store_snapshot(db, page, "http", failure=exc)
    return _store_snapshot(db, page, "http", fetched=fetched)


def snapshot_view(db, snapshot):
    return {**serialize(snapshot), "findings": [serialize(item) for item in rows(db, models.PageFinding, snapshot_id=snapshot.id)]}


class HtmlImport(Payload):
    html: str = Field(min_length=1, max_length=MAX_BYTES)
    source_note: str = Field(min_length=1, max_length=4000)

    @field_validator("html")
    @classmethod
    def bounded_html(cls, value):
        if len(value.encode("utf-8")) > MAX_BYTES:
            raise ValueError("HTML超过字节上限")
        return value

    @field_validator("source_note")
    @classmethod
    def note(cls, value):
        if not value.strip():
            raise ValueError("人工导入必须提供来源说明")
        return value.strip()


@router.post("/pages/{identifier}/fetch")
def fetch_page(identifier: int, db=Depends(get_db)):
    return snapshot_view(db, capture_page(db, require(db, models.Page, identifier)))


@router.post("/pages/{identifier}/import-html")
def import_html(identifier: int, payload: HtmlImport, db=Depends(get_db)):
    page = require(db, models.Page, identifier)
    return snapshot_view(db, _store_snapshot(db, page, "manual_import", html=payload.html, source_note=payload.source_note))


@router.get("/pages/{identifier}/snapshots")
def page_snapshots(identifier: int, db=Depends(get_db)):
    require(db, models.Page, identifier)
    return [snapshot_view(db, snapshot) for snapshot in rows(db, models.PageSnapshot, page_id=identifier)]


@router.get("/page-snapshots/{identifier}")
def page_snapshot(identifier: int, db=Depends(get_db)):
    return snapshot_view(db, require(db, models.PageSnapshot, identifier))

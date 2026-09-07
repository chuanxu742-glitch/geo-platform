import hashlib
import shutil
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models, website
from backend.app.db import get_db


@pytest.fixture
def peer(monkeypatch):
    state = {"requests": [], "html": '<html><head><title>Actual page</title><meta name="description" content="Observed summary"><link rel="canonical" href="/page"></head><body><h1>Service</h1><p>Public text</p></body></html>', "robots": "User-agent: *\nDisallow: /\nUser-agent: OAI-SearchBot\nAllow: /\nUser-agent: GPTBot\nDisallow: /\nUser-agent: Googlebot\nAllow: /", "robots_status": 200}
    state["posts"] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            state["posts"].append({"path": self.path, "body": body, "auth": self.headers.get("Authorization"), "host": self.headers.get("Host")})
            status = 302 if self.path == "/post-redirect" else 401 if self.path == "/unauthorized" else 201
            raw = b'{"id":1}' if status == 201 else b'{"code":"denied"}'
            self.send_response(status)
            self.send_header("Location", state["base"] + "/must-not-receive-credentials")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_GET(self):
            state["requests"].append((self.path, self.headers.get("Host")))
            if self.path in ("/redirect-private", "/loop", "/redirect"):
                self.send_response(302)
                self.send_header("Location", {"/redirect-private": "http://127.0.0.1:1/private", "/loop": "/loop", "/redirect": "/page"}[self.path])
                self.end_headers()
                return
            if self.path == "/error":
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"password=must-not-leak")
                return
            if self.path == "/large":
                self.send_response(200)
                self.send_header("Content-Length", str(website.MAX_BYTES + 1))
                self.end_headers()
                return
            if self.path in ("/stream-large", "/slow"):
                self.send_response(200)
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b"x" * (10 if self.path == "/slow" else 128))
                        self.wfile.flush()
                        if self.path == "/slow":
                            time.sleep(0.02)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                return
            raw = (state["robots"] if self.path == "/robots.txt" else state["html"]).encode()
            self.send_response(state["robots_status"] if self.path == "/robots.txt" else 200)
            self.send_header("Content-Type", "text/plain" if self.path == "/robots.txt" else "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Set-Cookie", "session=must-not-leak")
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["base"] = f"http://127.0.0.1:{server.server_port}"
    state["port"] = server.server_port
    monkeypatch.setenv("GEO_HTTP_ALLOWLIST", f"127.0.0.1:{server.server_port}")
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def api(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "website.db").as_posix(), connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def database():
        with sessions() as db:
            yield db

    app = FastAPI()
    app.include_router(website.router, prefix="/api")
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, sessions
    engine.dispose()


def register(api, url):
    with api[1]() as db:
        project = models.Project(name="Site", brand="Site", website_url=url)
        db.add(project)
        db.flush()
        page = models.Page(project_id=project.id, url=url)
        db.add(page)
        db.commit()
        return page.id


def test_real_fetch_snapshots_remain_immutable_and_reads_do_not_fetch(api, peer):
    client, _ = api
    page_id = register(api, peer["base"] + "/redirect")
    first = client.post(f"/api/pages/{page_id}/fetch").json()
    assert first["status"] == "success"
    assert first["final_url"] == peer["base"] + "/page"
    assert first["visible_text"] == "Service Public text"
    assert first["title"] == "Actual page"
    assert first["meta_description"] == "Observed summary"
    assert first["content_hash"] == hashlib.sha256(peer["html"].encode()).hexdigest()
    assert first["robots_txt"]["agents"] == {"OAI-SearchBot": True, "GPTBot": False, "Googlebot": True}
    training = next(item for item in first["findings"] if item["evidence"].get("agent") == "GPTBot")
    assert training["severity"] == "info" and training["evidence"]["purpose"] == "training"
    assert "set-cookie" not in first["fetch_evidence"]["headers"]
    peer["html"] = "<h1>Changed</h1>"
    second = client.post(f"/api/pages/{page_id}/fetch").json()
    assert second["visible_text"] == "Changed" and second["id"] != first["id"]
    requests = list(peer["requests"])
    assert client.get(f'/api/page-snapshots/{first["id"]}').json() == first
    assert client.get(f"/api/pages/{page_id}/snapshots").json() == [first, second]
    assert peer["requests"] == requests
    assert client.patch(f'/api/page-snapshots/{first["id"]}', json={"html": "edited"}).status_code == 405


def test_import_is_not_network_evidence_and_excludes_hidden_body(api, monkeypatch):
    client, _ = api
    page_id = register(api, "https://example.com/page")

    def forbidden(*args, **kwargs):
        pytest.fail("Manual import or read performed a network request")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    html = '<head><title>Private title</title><script type="application/ld+json">{"text":"JSON secret"}</script></head><h1>Visible<span hidden>secret</span></h1><p>Hel<b>lo</b> world</p><script>script secret</script><style>style secret</style><template>template secret</template><noscript>noscript secret</noscript><div hidden><div>hidden secret</div></div><p aria-hidden="true">aria secret</p><p style="display: none !important">display secret</p><p style="visibility: hidden">visibility secret</p><script type="application/ld+json">{bad}</script>'
    response = client.post(f"/api/pages/{page_id}/import-html", json={"html": html, "source_note": "Operator supplied saved source"})
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["source_kind"] == "manual_import" and snapshot["http_status"] is None
    assert snapshot["visible_text"] == "Visible Hello world"
    assert snapshot["headings"][0]["text"] == "Visible"
    assert snapshot["json_ld"] == [{"text": "JSON secret"}]
    assert snapshot["robots_txt"]["status"] == "unknown"
    assert all(value is None for value in snapshot["robots_txt"]["agents"].values())
    kinds = {item["kind"] for item in snapshot["findings"]}
    assert {"missing_meta_description", "missing_canonical", "invalid_json_ld"} <= kinds
    assert all(item["evidence"]["location"] and item["evidence"]["source_kind"] == "manual_import" for item in snapshot["findings"])
    assert "score" not in str(snapshot).lower()
    assert client.get(f'/api/page-snapshots/{snapshot["id"]}').json() == snapshot


@pytest.mark.parametrize("path,code", [("/redirect-private", "destination_not_public"), ("/loop", "too_many_redirects"), ("/large", "response_too_large"), ("/error", "http_status_failure")])
def test_fetch_failures_persist_unknown_not_low_scores(api, peer, path, code):
    client, _ = api
    page_id = register(api, peer["base"] + path)
    response = client.post(f"/api/pages/{page_id}/fetch")
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["status"] == "failure" and snapshot["error"] == code
    assert snapshot["visible_text"] == "" and snapshot["content_hash"] == ""
    assert snapshot["findings"] == []
    assert snapshot["robots_txt"]["status"] == "unknown"
    assert "must-not-leak" not in str(snapshot) and "score" not in str(snapshot).lower()
    assert client.get(f'/api/page-snapshots/{snapshot["id"]}').json() == snapshot
    assert all(path != "/private" and path != "/robots.txt" for path, _ in peer["requests"])


def test_missing_robots_is_unknown_not_allowed(api, peer):
    peer["robots_status"] = 404
    page_id = register(api, peer["base"] + "/page")
    snapshot = api[0].post(f"/api/pages/{page_id}/fetch").json()
    assert snapshot["status"] == "success"
    assert snapshot["robots_txt"]["status"] == "unknown"
    assert snapshot["robots_txt"]["agents"] == dict.fromkeys(website.AGENTS)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://user:password@example.com", "http://example.com\\@127.0.0.1", "http://example.com\n", "http://example.com:99999", "http://[fe80::1%25eth0]/"])
def test_invalid_urls_rejected(url):
    with pytest.raises(HTTPException) as exc:
        website.validate_url(url)
    assert exc.value.status_code == 422


def test_all_dns_answers_checked_and_override_is_exact(monkeypatch):
    monkeypatch.setenv("GEO_HTTP_ALLOWLIST", "example.com.evil:80")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))])
    with pytest.raises(website.FetchError, match="destination_not_public"):
        website.fetch_url("http://example.com/")


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.100.100.200", "::1", "::ffff:127.0.0.1", "fc00::1", "224.0.0.1", "64:ff9b::7f00:1", "2002:7f00:1::"])
def test_private_and_metadata_dns_targets_denied(monkeypatch, ip):
    monkeypatch.delenv("GEO_HTTP_ALLOWLIST", raising=False)
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(family, socket.SOCK_STREAM, 6, "", (ip, 80))])
    with pytest.raises(website.FetchError, match="destination_not_public"):
        website.fetch_url("http://site.example/")


def test_dns_rebinding_cannot_change_transport_and_host_is_preserved(peer, monkeypatch):
    monkeypatch.setenv("GEO_HTTP_ALLOWLIST", f"site.example:{peer['port']}")
    calls = []

    def resolve(host, port, **kwargs):
        calls.append(host)
        if len(calls) > 1:
            pytest.fail("Transport re-resolved a validated hostname")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    response = website.fetch_url(f"http://site.example:{peer['port']}/page")
    assert response["html"] == peer["html"]
    assert peer["requests"] == [("/page", f"site.example:{peer['port']}")]
    assert calls == ["site.example"]


def test_unannounced_body_size_and_total_deadline_are_bounded(peer, monkeypatch):
    monkeypatch.setattr(website, "MAX_BYTES", 100)
    with pytest.raises(website.FetchError, match="response_too_large"):
        website.fetch_url(peer["base"] + "/stream-large")
    monkeypatch.setattr(website, "MAX_BYTES", 100000)
    monkeypatch.setattr(website, "FETCH_TIMEOUT", 0.12)
    start = time.monotonic()
    with pytest.raises(website.FetchError):
        website.fetch_url(peer["base"] + "/slow")
    assert time.monotonic() - start < 1.0


def test_robots_specific_groups_longest_rule_and_search_training_are_separate():
    content = "User-agent: *\nDisallow: /\nUser-agent: GPTBot\nDisallow: /\nUser-agent: OAI-SearchBot\nDisallow: /docs/*\nAllow: /docs/public$\nUser-agent: Googlebot\nDisallow: /docs\nUser-agent: Googlebot\nAllow: /docs/public"
    assert website._robots_rules(content, "https://example.com/docs/public") == {"OAI-SearchBot": True, "GPTBot": False, "Googlebot": True}
    assert website._robots_rules(content, "https://example.com/docs/public/private") == {"OAI-SearchBot": False, "GPTBot": False, "Googlebot": True}


def test_tls_uses_original_hostname_for_sni_and_certificate_validation(tmp_path, monkeypatch):
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("Local TLS certificate generation requires openssl")
    cert, key = tmp_path / "peer.crt", tmp_path / "peer.key"
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=site.example", "-addext", "subjectAltName=DNS:site.example"], check=True, capture_output=True)
    names = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "6")
            self.end_headers()
            self.wfile.write(b"secure")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    context.set_servername_callback(lambda sock, name, ctx: names.append(name))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_context = ssl.create_default_context
    monkeypatch.setattr(ssl, "create_default_context", lambda: original_context(cafile=str(cert)))
    monkeypatch.setenv("GEO_HTTP_ALLOWLIST", f"site.example:{server.server_port},wrong.example:{server.server_port}")
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))])
    try:
        assert website.fetch_url(f"https://site.example:{server.server_port}/")["html"] == "secure"
        with pytest.raises(website.FetchError, match="transport_failure"):
            website.fetch_url(f"https://wrong.example:{server.server_port}/")
        assert names == ["site.example", "wrong.example"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("html,error", [
    ("<div>" * 257 + "untrusted", "html_complexity_limit"),
    ('<script type="application/ld+json">' + "[" * 65 + "0" + "]" * 65 + "</script>", "json_ld_complexity_limit"),
])
def test_excessive_nesting_is_failure_not_fabricated_diagnostics(api, html, error):
    page_id = register(api, "https://example.com/page")
    response = api[0].post(f"/api/pages/{page_id}/import-html", json={"html": html, "source_note": "Oversized nesting"})
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["status"] == "failure" and snapshot["error"] == error
    assert snapshot["findings"] == [] and snapshot["visible_text"] == ""


def test_authenticated_request_is_single_hop_and_preserves_failure_status(peer):
    headers = {"Authorization": "Basic local-test-only", "Content-Type": "application/json", "HOST": "wrong.example"}
    body = b'{"content":"approved"}'
    response = website.request_url(peer["base"] + "/create", method="POST", body=body, headers=headers)
    assert response["http_status"] == 201 and response["html"] == '{"id":1}'
    denied = website.request_url(peer["base"] + "/unauthorized", method="POST", body=body, headers=headers)
    assert denied["http_status"] == 401 and denied["html"] == '{"code":"denied"}'
    redirect = website.request_url(peer["base"] + "/post-redirect", method="POST", body=body, headers=headers)
    assert redirect["http_status"] == 302
    assert [item["path"] for item in peer["posts"]] == ["/create", "/unauthorized", "/post-redirect"]
    assert peer["requests"] == []
    assert all(item["body"] == body and item["auth"] == headers["Authorization"] and item["host"] == f"127.0.0.1:{peer['port']}" for item in peer["posts"])
    assert "local-test-only" not in str(response) + str(denied) + str(redirect)


def test_local_http_exception_requires_literal_loopback_and_exact_port(peer, monkeypatch):
    assert website.controlled_local_url(peer["base"])
    assert not website.controlled_local_url("http://127.0.0.1:1")
    monkeypatch.setenv("GEO_HTTP_ALLOWLIST", "localhost:80,10.0.0.1:80,example.com:80")
    assert not website.controlled_local_url("http://localhost")
    assert not website.controlled_local_url("http://10.0.0.1")
    assert not website.controlled_local_url("http://example.com")


def test_approved_html_normalization_cannot_use_nonvisible_content():
    assert website.visible_text('<h1>Public</h1><p>Approved <strong>draft</strong>.</p><script>wrong</script><p hidden>wrong</p>') == "Public Approved draft."
    assert website.visible_text("Approved plain text") == "Approved plain text"
    assert website.visible_text('<head><title>Wrong</title></head><script type="application/ld+json">{"text":"Wrong"}</script><style>Wrong</style>') == ""

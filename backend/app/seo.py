"""Static SEO observations. Targets are inspected as strings, never fetched."""
import re
from urllib.parse import urljoin, urlsplit


def technical_findings(page_url, parser):
    from .website import validate_url
    from fastapi import HTTPException

    findings = []
    base = urljoin(page_url, parser.base_href) if parser.base_href else page_url

    def resolve(href):
        if not href.strip():
            return None
        try:
            return validate_url(urljoin(base, href))
        except HTTPException:
            return None

    def add(kind, title, location, observed, recommendation, severity="warning"):
        findings.append(dict(kind=kind, title=title, location=location, observed=observed,
                             recommendation=recommendation, severity=severity,
                             category="technical_seo", execution="website_code",
                             acceptance="重新抓取目标页，核对HTML声明；实际收录另用站长工具确认。"))

    if len(parser.canonical_links) > 1:
        add("multiple_canonicals", "页面声明了多个规范链接", "document: canonical links",
            parser.canonical_links, "保留一个符合页面用途的规范链接，并核对模板是否重复注入。")
    for link in parser.canonical_links:
        target = resolve(link["href"])
        if target is None:
            add("invalid_canonical", "规范链接为空或不是有效HTTP(S)地址", link["location"], link["href"],
                "在页面head修正规范网址。正文改稿不能修复这个问题。")
        elif target != validate_url(page_url):
            add("canonical_other_page", "规范链接指向其他页面，需核对合并意图", link["location"],
                {"page_url": page_url, "canonical_url": target},
                "如果本页是独立服务、路线或案例页，规范链接应指向本页；若为有意合并的重复页则保留。不能据此断言已被搜索引擎合并。")

    def language_root(url):
        parts = urlsplit(url).path.strip("/").split("/")
        return len(parts) == 1 and bool(re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*", parts[0]))

    seen = {}
    for link in parser.hreflang_links:
        language = link["language"].lower()
        target = resolve(link["href"])
        if target is None:
            add("invalid_hreflang_url", "多语言对应地址无效", link["location"], link,
                "将多语言地址改为真实存在的同内容语言版本；不自动创建翻译页面。")
            continue
        if language in seen and seen[language] != target:
            add("conflicting_hreflang", "同一语言声明了不同对应页面", link["location"], link,
                "每个语言标记保留一致的对应页面，并检查对方页面的回链。")
        seen[language] = target
        if len(urlsplit(page_url).path.strip("/").split("/")) > 1 and language_root(target) and language != "x-default":
            add("hreflang_homepage_review", "子页面的语言版本指向语言首页", link["location"], link,
                "核对是否应对应同一内容的翻译页，例如中文FAQ对应英文FAQ。本项是路径启发式提示，未核验目标正文或双向声明。")
    return findings

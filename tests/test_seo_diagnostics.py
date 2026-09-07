from backend.app.website import _parse_html
from backend.app.seo import technical_findings
from test_website_operations import api, register


def diagnose(html, url="https://example.com/zh/faq"):
    return technical_findings(url, _parse_html(html))


def test_reference_pattern_is_reported_without_claiming_indexing_failure():
    findings = diagnose('<link rel="canonical" href="/zh"><link rel="alternate" hreflang="en" href="/en">')
    assert {f['kind'] for f in findings} == {'canonical_other_page', 'hreflang_homepage_review'}
    assert all(f['execution'] == 'website_code' for f in findings)
    assert findings[0]['observed']['canonical_url'] == 'https://example.com/zh'


def test_valid_relative_canonical_and_translated_slug_are_not_flagged():
    assert diagnose('<link rel="canonical" href="faq"><link rel="alternate" hreflang="en" href="/en/questions">') == []


def test_homepage_and_x_default_are_not_false_positives():
    assert diagnose('<link rel="canonical" href="/zh"><link rel="alternate" hreflang="en" href="/en">', 'https://example.com/zh') == []
    assert diagnose('<link rel="alternate" hreflang="x-default" href="/en">') == []


def test_conflicting_and_invalid_metadata():
    findings = diagnose('<link rel="canonical" href="javascript:alert(1)"><link rel="canonical" href="/zh/faq"><link rel="alternate" hreflang="en" href="/en/faq"><link rel="alternate" hreflang="EN" href="/en/other"><link rel="alternate" hreflang="fr" href="">')
    assert {f['kind'] for f in findings} == {'multiple_canonicals', 'invalid_canonical', 'conflicting_hreflang', 'invalid_hreflang_url'}


def test_base_and_redirect_destination_are_respected():
    assert diagnose('<base href="https://example.com/zh/"><link rel="canonical" href="faq">') == []
    assert diagnose('<link rel="canonical" href="https://example.com/zh/faq#top">') == []


def test_metadata_is_persisted_and_old_snapshot_keeps_its_findings(api):
    client, _ = api
    page_id = register(api, 'https://example.com/zh/faq')
    endpoint = f'/api/pages/{page_id}/import-html'
    first = client.post(endpoint, json={'html': '<link rel="canonical" href="/zh"><link rel="alternate" hreflang="en" href="/en"><h1>FAQ</h1>', 'source_note': 'Synthetic reference pattern, not customer data'}).json()
    assert first['fetch_evidence']['seo_metadata']['hreflang_links'][0]['href'] == '/en'
    finding = next(f for f in first['findings'] if f['kind'] == 'canonical_other_page')
    assert finding['evidence']['execution'] == 'website_code'
    assert finding['evidence']['source_kind'] == 'manual_import'
    second = client.post(endpoint, json={'html': '<link rel="canonical" href="/zh/faq"><h1>FAQ</h1>', 'source_note': 'Corrected synthetic metadata'}).json()
    assert not any(f['kind'] == 'canonical_other_page' for f in second['findings'])
    assert client.get(f'/api/page-snapshots/{first["id"]}').json() == first

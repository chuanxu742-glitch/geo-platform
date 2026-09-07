"""Exercise registered API, auth and project history, not standalone routers only."""
from test_contract import client, call


def test_imported_business_evidence_survives_repeat_and_project_delete(client):
    project = call(client, 'POST', '/projects', {'name': 'Synthetic business', 'brand': 'Example'}, 201)
    path = f'/projects/{project["id"]}/measurements'
    payload = {'source_label': 'Synthetic search export', 'rows': [{
        'date': '2026-09-01', 'page_url': 'https://example.com/service',
        'channel': 'seo', 'query': 'service cost', 'impressions': 20, 'clicks': 2,
        'leads': None, 'orders': 0}]}
    first = client.post('/api' + path + '/import', json=payload)
    assert first.status_code in (200, 201), first.text
    assert call(client, 'GET', path)['summary'] == {'impressions': 20, 'clicks': 2, 'leads': None, 'orders': 0}
    second = client.post('/api' + path + '/import', json=payload)
    assert second.status_code in (200, 201)
    assert len(call(client, 'GET', path)['rows']) == 1
    call(client, 'DELETE', f'/projects/{project["id"]}', code=409)
    assert len(call(client, 'GET', path)['rows']) == 1


def test_measurement_routes_require_configured_token(client, monkeypatch):
    monkeypatch.setenv('GEO_BACKEND_TOKEN', 'synthetic-test-token')
    assert client.get('/api/projects/1/measurements').status_code == 401
    assert client.post('/api/projects/1/measurements/import', json={'source_label': 'test', 'rows': [{
        'date': '2026-09-01', 'page_url': 'https://example.com/', 'channel': 'seo'}]}).status_code == 401

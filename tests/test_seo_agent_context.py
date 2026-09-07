from test_agent_runtime import client, agent_site, start, call


def test_plan_receives_frozen_page_diagnostics_and_business_guidance(client, agent_site):
    run = start(client, agent_site)
    assert run['status'] == 'awaiting_review', run
    payload = next(c for c in agent_site[2]['model_calls'] if 'optimization_guidance' in c)
    assert payload['optimization_guidance']['reference_boundary']
    assert payload['optimization_guidance']['content_opportunities']
    assert payload['snapshots']
    for snapshot in payload['snapshots']:
        assert 'canonical' in snapshot and 'headings' in snapshot
        assert snapshot['seo_findings']
        assert all(f['snapshot_id'] == snapshot['id'] for f in snapshot['seo_findings'])
    assert agent_site[2]['posts'] == []
    call(client, 'POST', f'/agent-runs/{run["id"]}/cancel')

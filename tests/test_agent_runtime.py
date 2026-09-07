import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_contract import client, call
from agent_peer import controlled_agent_peer
from backend.app import agent_runtime


def wait_run(client, identifier, status=None):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        run = call(client, 'GET', f'/agent-runs/{identifier}')
        if run['status'] in ({status} if status else {'awaiting_review', 'blocked', 'failed', 'completed', 'cancelled'}):
            return run
        time.sleep(.02)
    raise AssertionError(run)


@pytest.fixture
def agent_site(client, monkeypatch):
    with controlled_agent_peer() as (url, state):
        for key, value in {'OPENAI_API_KEY': 'controlled-not-real', 'OPENAI_MODEL': 'controlled-protocol', 'OPENAI_BASE_URL': url + '/v1',
            'WORDPRESS_URL': url, 'WORDPRESS_USERNAME': 'fixture-account', 'WORDPRESS_APPLICATION_PASSWORD': 'fixture-password',
            'GEO_HTTP_ALLOWLIST': url.removeprefix('http://'), 'RAZORMIND_URL': url}.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(agent_runtime, 'POLL_SECONDS', .02)
        p = call(client, 'POST', '/projects', {'name': '真实协议测试', 'brand': 'Alpha', 'website_url': url}, 201)
        call(client, 'POST', f'/projects/{p["id"]}/publishers', {'name': '目标页', 'site_url': url, 'resource': 'pages', 'post_id': 17}, 201)
        yield p, url, state


def start(client, site, sample=False):
    p, _, _ = site
    run = call(client, 'POST', f'/projects/{p["id"]}/agent-runs', {'goal': '明确安装范围帮助客户判断适配', 'policy': {'max_pages': 1, 'sample': sample}}, 201)
    return wait_run(client, run['id'])


def approval_body(run, decision, feedback='确认当前显示版本与动作'):
    proposal = run['current_proposal']
    return {'proposal_id': proposal['id'], 'decision': decision, 'reviewer': '测试审核人', 'feedback': feedback,
        'allow_publish': decision == 'approve_and_publish',
        'bindings': [{k: d[k] for k in ('page_id', 'content_version_id', 'target_url', 'body_hash', 'title')} for d in proposal['drafts']] if decision == 'approve_and_publish' else []}


def review(client, run, decision, feedback='确认当前显示版本与动作', code=200):
    return call(client, 'POST', f'/agent-runs/{run["id"]}/approvals', approval_body(run, decision, feedback), code)


def draft(client, site):
    run = start(client, site)
    assert run['current_proposal']['kind'] == 'plan', run
    review(client, run, 'approve')
    run = wait_run(client, run['id'])
    assert run['current_proposal']['kind'] == 'drafts', run
    return run


def test_missing_model_never_creates_fake_run(client):
    p = call(client, 'POST', '/projects', {'name': '无模型', 'brand': 'Alpha', 'website_url': 'https://example.com'}, 201)
    caps = call(client, 'GET', f'/projects/{p["id"]}/agent-capabilities')
    assert caps['model_ready'] is False and caps['ready'] is False
    call(client, 'POST', f'/projects/{p["id"]}/agent-runs', {'goal': '优化官网'}, 503)
    assert call(client, 'GET', f'/projects/{p["id"]}/agent-runs') == []


@pytest.mark.parametrize('mode', ['cross_url', 'bad_quote', 'active_html'])
def test_untrusted_model_cannot_expand_scope_or_execute_markup(client, agent_site, mode):
    agent_site[2]['model_mode'] = mode
    run = start(client, agent_site)
    if mode == 'active_html':
        review(client, run, 'approve')
        run = wait_run(client, run['id'])
    assert run['status'] == 'blocked', run
    assert agent_site[2]['posts'] == []
    assert not any(p['kind'] == 'drafts' for p in run['proposals'])


def test_approve_only_and_concurrent_stale_approval_never_publish(client, agent_site):
    run = draft(client, agent_site)
    payload = approval_body(run, 'approve_only')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(f'/api/agent-runs/{run["id"]}/approvals', json=payload), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    pending = wait_run(client, run['id'])
    assert pending['current_proposal']['kind'] == 'publication_authorization'
    assert agent_site[2]['posts'] == []
    call(client, 'POST', f'/agent-runs/{run["id"]}/cancel')
    review(client, pending, 'approve_and_publish', code=409)
    assert agent_site[2]['posts'] == []


def test_changed_title_rejects_publish_but_allows_refusal(client, agent_site):
    run = draft(client, agent_site)
    content_id = run['current_proposal']['drafts'][0]['content_id']
    call(client, 'PATCH', f'/contents/{content_id}', {'title': '高级编辑已更换标题'})
    review(client, run, 'approve_and_publish', code=409)
    rejected = review(client, run, 'reject', '标题不一致，拒绝旧稿')
    assert rejected['status'] == 'cancelled' and agent_site[2]['posts'] == []


def test_stale_wordpress_body_blocks_write(client, agent_site):
    run = draft(client, agent_site)
    agent_site[2]['body'] = '其他编辑已更新官网，禁止覆盖。'
    review(client, run, 'approve_and_publish')
    run = wait_run(client, run['id'])
    assert run['status'] == 'blocked' and '陈旧' in run['blocked_reason']
    assert agent_site[2]['posts'] == []


def test_revision_unknown_submission_and_checkpoint_recovery_write_once(client, agent_site):
    run = draft(client, agent_site)
    original_id = run['current_proposal']['drafts'][0]['content_version_id']
    review(client, run, 'request_changes', '更简洁')
    run = wait_run(client, run['id'])
    assert run['current_proposal']['drafts'][0]['content_version_id'] != original_id
    agent_site[2]['mode'] = 'unknown'
    review(client, run, 'approve_and_publish')
    run = wait_run(client, run['id'])
    assert run['status'] == 'completed' and run['outcomes'][0]['status'] == 'verified', run
    assert len(agent_site[2]['posts']) == 1
    original_facts = call(client, 'GET', f'/projects/{agent_site[0]["id"]}/facts')
    followup = draft(client, agent_site)
    followup_draft = followup['current_proposal']['drafts'][0]
    assert call(client, 'GET', f'/projects/{agent_site[0]["id"]}/facts') == original_facts
    assert followup_draft['fact_ids'] == [f['id'] for f in original_facts]
    call(client, 'POST', f'/agent-runs/{followup["id"]}/cancel')
    calls = len(agent_site[2]['model_calls'])
    agent_runtime._worker.stop()
    worker = agent_runtime.start_worker()
    try:
        time.sleep(.1)
        after = call(client, 'GET', f'/agent-runs/{run["id"]}')
        assert after['outcomes'] == run['outcomes']
        assert len(agent_site[2]['posts']) == 1 and len(agent_site[2]['model_calls']) == calls
    finally:
        worker.stop()


def test_authorized_sampling_pending_to_complete_without_manual_sync(client, agent_site):
    p, _, state = agent_site
    call(client, 'POST', f'/projects/{p["id"]}/sources', {'name': '受控采集', 'platform': '受控平台', 'source_id': 'fixture', 'answer_complete': True}, 201)
    run = start(client, agent_site, sample=True)
    review(client, run, 'approve')
    run = wait_run(client, run['id'])
    review(client, run, 'approve_and_publish')
    run = wait_run(client, run['id'])
    assert run['status'] == 'completed', run
    assert [p['status'] for p in state['polls']] == ['pending', 'completed', 'pending', 'completed']
    assert len(state['tasks']) == 2 and len(state['posts']) == 1
    assert run['observation']['status'] == 'descriptive_comparison'
    comparison = run['observation']['comparison']
    baseline = call(client, 'GET', f'/batches/{comparison["baseline_batch_id"]}')
    retest = call(client, 'GET', f'/batches/{comparison["retest_batch_id"]}')
    job = call(client, 'GET', f'/publication-jobs/{run["outcomes"][0]["publication_job_id"]}')
    assert baseline['answers'][0]['observed_at'] < job['created_at'] < job['verified_at'] < retest['answers'][0]['observed_at']


@pytest.mark.parametrize('change', ['fact', 'cancel'])
def test_model_return_cannot_refreeze_edited_facts_or_revive_cancelled_run(client, agent_site, change):
    run = start(client, agent_site)
    state = agent_site[2]
    state['hold_draft'] = True
    review(client, run, 'approve')
    deadline = time.monotonic() + 10
    while not state['draft_waiting'] and time.monotonic() < deadline:
        time.sleep(.02)
    assert state['draft_waiting']
    try:
        if change == 'fact':
            facts = call(client, 'GET', f'/projects/{agent_site[0]["id"]}/facts')
            call(client, 'PATCH', f'/facts/{facts[0]["id"]}', {'claim': '审核后事实已更改，不得配旧模型稿'})
        else:
            call(client, 'POST', f'/agent-runs/{run["id"]}/cancel')
    finally:
        state['hold_draft'] = False
    time.sleep(.3)
    run = wait_run(client, run['id'])
    assert run['status'] == ('blocked' if change == 'fact' else 'cancelled')
    assert not any(p['kind'] == 'drafts' for p in run['proposals'])
    assert all(not c['versions'] for c in call(client, 'GET', f'/projects/{agent_site[0]["id"]}/contents'))
    assert state['posts'] == []


def test_unexpected_worker_error_is_unready_and_does_not_echo_exception(client, agent_site, monkeypatch):
    agent_runtime._worker.stop()
    worker = agent_runtime.Executor()
    def failure():
        raise NameError('sensitive-upstream-value')
    worker.schedule_due = failure
    monkeypatch.setattr(agent_runtime, '_worker', worker)
    worker.start()
    worker.thread.join(timeout=2)
    health = call(client, 'GET', '/agent-worker/health')
    assert health['running'] is False and 'NameError' in health['reason']
    assert 'sensitive-upstream-value' not in health['reason']
    caps = call(client, 'GET', f'/projects/{agent_site[0]["id"]}/agent-capabilities')
    assert caps['ready'] is False and caps['worker_ready'] is False
    call(client, 'POST', f'/projects/{agent_site[0]["id"]}/agent-runs', {'goal': '后台不可用时不得假启动'}, 503)

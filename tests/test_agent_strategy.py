"""Observable GEO business contracts using loopback protocol peers, not model quality claims."""
import time
import pytest
from test_agent_runtime import client, agent_site, start, review, wait_run, draft, call
from backend.app import agent_runtime
from backend.app.models import AgentRun


def source(client, project):
    return call(client, 'POST', f'/projects/{project["id"]}/sources',
        {'name': 'controlled', 'platform': 'controlled', 'source_id': 'fixture', 'answer_complete': True}, 201)


def test_answer_changes_strategy_and_real_draft_before_publication(client, agent_site):
    first, url, state = agent_site
    results = []
    for index, text in enumerate(['安装服务包括现场安装与使用说明。', 'Alpha不提供现场安装，仅提供远程说明。']):
        project = first if not index else call(client, 'POST', '/projects',
            {'name': 'same scope', 'brand': first['brand'], 'website_url': url}, 201)
        source(client, project)
        state['answer_text'] = text
        run = start(client, (project, url, state), sample=True)
        review(client, run, 'approve')
        run = wait_run(client, run['id'])
        assert run['status'] == 'awaiting_review', run
        proposal = run['current_proposal']
        item = proposal['drafts'][0]
        strategy = item['generation']['strategy']
        judgment = strategy['targets'][0]['judgments'][0]
        citation = judgment['answer_evidence'][0]
        assert citation['quote'] == text
        answer = call(client, 'GET', f'/answers/{citation["answer_id"]}')
        assert answer['text'][citation['start']:citation['end']] == text
        assert answer['analyses'][0]['recommendation'] == 'unknown'
        assert answer['analyses'][0]['factual_status'] == 'unknown'
        assert state['posts'] == []
        latest_draft = [e for e in state['events'] if e.get('stage') == 'draft'][-1]
        assert state['polls'][-1]['status'] == 'completed'
        assert state['polls'][-1]['at'] < latest_draft['at']
        assert text in state['model_calls'][-1]['instructions']
        results.append((item, judgment))
        call(client, 'POST', f'/agent-runs/{run["id"]}/cancel')
    assert results[0][1]['problem_type'] == 'brand_absent'
    assert results[1][1]['problem_type'] == 'fact_mismatch'
    for field in ('after_text', 'expected_change', 'acceptance_method'):
        assert results[0][0][field] != results[1][0][field]


@pytest.mark.parametrize('mode', ['strategy_quote', 'strategy_answer', 'strategy_fact', 'strategy_url', 'strategy_absence_fragment', 'strategy_inconclusive'])
def test_invalid_strategy_cannot_create_draft_or_publish(client, agent_site, mode):
    source(client, agent_site[0])
    agent_site[2]['model_mode'] = mode
    run = start(client, agent_site, sample=True)
    review(client, run, 'approve')
    run = wait_run(client, run['id'])
    assert run['status'] == 'blocked', run
    assert not any(p['kind'] == 'drafts' for p in run['proposals'])
    assert agent_site[2]['posts'] == []
    assert not any(e.get('stage') == 'draft' for e in agent_site[2]['events'])


def test_hypothesis_is_visible_and_strategy_counts_against_budget(client, agent_site):
    run = draft(client, agent_site)
    proposal = run['current_proposal']
    assert '无匹配AI回答证据' in proposal['summary']
    assert '无匹配AI回答证据' in proposal['drafts'][0]['acceptance_method']
    call(client, 'POST', f'/agent-runs/{run["id"]}/cancel')
    limited = call(client, 'POST', f'/projects/{agent_site[0]["id"]}/agent-runs',
        {'goal': 'bounded', 'policy': {'max_pages': 1, 'max_model_requests': 3}}, 201)
    limited = wait_run(client, limited['id'])
    review(client, limited, 'approve')
    limited = wait_run(client, limited['id'])
    assert limited['status'] == 'blocked' and '预算' in limited['blocked_reason']
    assert len([s for s in limited['steps'] if s['kind'] in agent_runtime.MODEL_KINDS]) == 3
    assert not any(p['kind'] == 'drafts' for p in limited['proposals'])


def test_legacy_approved_unwritten_draft_requires_new_review(client, agent_site):
    run = draft(client, agent_site)
    old = run['current_proposal']
    agent_runtime._worker.stop()
    review(client, run, 'approve_and_publish')
    with agent_runtime.Session() as db:
        stored = db.get(AgentRun, run['id'])
        cp = dict(stored.checkpoint)
        cp.pop('strategy_step_id')
        cp.pop('strategy')
        stored.checkpoint = cp
        db.commit()
    worker = agent_runtime.start_worker()
    run = wait_run(client, run['id'])
    assert run['status'] == 'awaiting_review', run
    assert run['current_proposal']['kind'] == 'drafts'
    assert run['current_proposal']['id'] != old['id']
    assert run['current_proposal']['drafts'][0]['content_version_id'] != old['drafts'][0]['content_version_id']
    assert agent_site[2]['posts'] == []
    call(client, 'POST', f'/agent-runs/{run["id"]}/cancel')


def test_strategy_feedback_and_restart_do_not_repeat_baseline_or_refine(client, agent_site):
    source(client, agent_site[0])
    run = start(client, agent_site, sample=True)
    review(client, run, 'approve')
    run = wait_run(client, run['id'])
    strategy_id = run['current_proposal']['drafts'][0]['generation']['strategy_step_id']
    review(client, run, 'request_changes', '更简洁')
    run = wait_run(client, run['id'])
    assert run['current_proposal']['drafts'][0]['generation']['strategy_step_id'] == strategy_id
    assert len(agent_site[2]['tasks']) == 1
    assert len([c for c in agent_site[2]['model_calls'] if c.get('stage') == 'strategy']) == 1
    agent_runtime._worker.stop()
    worker = agent_runtime.start_worker()
    time.sleep(.1)
    assert len(agent_site[2]['tasks']) == 1
    assert len([c for c in agent_site[2]['model_calls'] if c.get('stage') == 'strategy']) == 1
    call(client, 'POST', f'/agent-runs/{run["id"]}/cancel')


def test_history_is_project_scoped_and_analysis_version_frozen_before_approval(client, agent_site):
    from test_contract import imported
    project, _, state = agent_site
    question = call(client, 'POST', f'/projects/{project["id"]}/questions',
        {'text': '安装服务包括哪些范围？', 'branded': False, 'intent': '服务范围适配'}, 201)
    batch = call(client, 'POST', f'/projects/{project["id"]}/batches',
        {'name': 'existing genuine imported evidence', 'question_ids': [question['id']], 'sampling': {'platforms': ['测试平台']}}, 201)
    raw = '其他供应商提供现场安装。'
    answer = imported(client, batch, question, raw)
    call(client, 'POST', f'/batches/{batch["id"]}/analyze', {'use_model': False})
    original = call(client, 'GET', f'/answers/{answer["id"]}')['analyses'][0]
    other = call(client, 'POST', '/projects', {'name': 'other', 'brand': 'Alpha'}, 201)
    other_q = call(client, 'POST', f'/projects/{other["id"]}/questions',
        {'text': question['current_version']['text'], 'branded': False}, 201)
    other_b = call(client, 'POST', f'/projects/{other["id"]}/batches',
        {'name': 'not this project', 'question_ids': [other_q['id']], 'sampling': {'platforms': ['测试平台']}}, 201)
    imported(client, other_b, other_q, 'CROSS_PROJECT_MUST_NOT_APPEAR')
    run = start(client, agent_site)
    plan_input = state['model_calls'][-1]
    assert plan_input['evidence_pool']['answers'][0]['text'] == raw
    assert all(a['batch_id'] != other_b['id'] for a in plan_input['evidence_pool']['answers'])
    call(client, 'POST', f'/batches/{batch["id"]}/analyze', {'use_model': False})
    review(client, run, 'approve')
    run = wait_run(client, run['id'])
    item = run['current_proposal']['drafts'][0]
    citation = item['generation']['strategy']['targets'][0]['judgments'][0]['answer_evidence'][0]
    assert citation['analysis_id'] == original['id']
    assert citation['analysis_version'] == original['version']
    assert citation['quote'] == raw
    assert raw in state['model_calls'][-1]['instructions']
    assert state['tasks'] == {} and state['posts'] == []
    call(client, 'POST', f'/agent-runs/{run["id"]}/cancel')


def test_legacy_external_write_recovers_without_new_model_or_post(client, agent_site):
    run = draft(client, agent_site)
    review(client, run, 'approve_and_publish')
    run = wait_run(client, run['id'])
    assert run['status'] == 'completed'
    agent_runtime._worker.stop()
    before = (len(agent_site[2]['model_calls']), len(agent_site[2]['posts']))
    with agent_runtime.Session() as db:
        stored = db.get(AgentRun, run['id'])
        cp = dict(stored.checkpoint)
        cp.pop('strategy_step_id')
        cp.pop('strategy')
        stored.checkpoint = cp
        stored.phase, stored.status = 'publish', 'queued'
        db.commit()
    agent_runtime.start_worker()
    recovered = wait_run(client, run['id'])
    assert recovered['status'] == 'completed', recovered
    assert recovered['observation']['status'] == 'legacy_observation_only'
    assert (len(agent_site[2]['model_calls']), len(agent_site[2]['posts'])) == before

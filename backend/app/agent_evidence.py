"""Frozen, bounded domain evidence for Agent planning; never a cross-mode ranking."""
from datetime import timedelta
from sqlalchemy import select
from .models import (Answer, Batch, Analysis, AnalysisRun, Diagnosis, Research, ResearchRevision,
                     OperationRule, Experiment, now)
from .common import serialize
from .analytics import latest_analyses, parse_time


MAX_ANSWERS = 12
MAX_TEXT = 12000
MAX_BATCHES = 6
MAX_AGE_DAYS = 180


def evidence_pool(db, project, question_ids=None, batch_id=None, analysis_run_id=None):
    cutoff = now() - timedelta(days=MAX_AGE_DAYS)
    query = select(Batch).where(Batch.project_id == project['id']).order_by(Batch.id.desc())
    if batch_id is not None:
        query = query.where(Batch.id == batch_id)
    batches = db.scalars(query.limit(MAX_BATCHES)).all()
    answers, selected_batches = [], []
    analysis_runs = {}
    excluded = {'invalid_or_incomplete': 0, 'conditions_or_question': 0, 'old_or_oversize': 0}
    for batch in batches:
        snapshot = batch.snapshot
        if snapshot.get('brand') != project['brand'] or snapshot.get('region', '') != project['region']:
            excluded['conditions_or_question'] += 1
            continue
        questions = {q['id']: q for q in snapshot.get('questions', [])}
        candidates = db.scalars(select(Answer).where(Answer.batch_id == batch.id).order_by(Answer.id.desc()).limit(100)).all()
        analyses = ({a.answer_id: a for a in db.scalars(select(Analysis).where(Analysis.run_id == analysis_run_id))}
                    if analysis_run_id is not None else latest_analyses(db, [a.id for a in candidates]))
        batch_answers = []
        for answer in candidates:
            if len(answers) + len(batch_answers) >= MAX_ANSWERS:
                break
            q = questions.get(answer.question_version_id)
            if not q or (question_ids is not None and q['question_id'] not in question_ids):
                excluded['conditions_or_question'] += 1
                continue
            if answer.validity != 'valid' or not answer.complete or not answer.text.strip():
                excluded['invalid_or_incomplete'] += 1
                continue
            observed = answer.observed_at or answer.created_at.isoformat()
            if parse_time(observed) < cutoff or len(answer.text) > MAX_TEXT:
                excluded['old_or_oversize'] += 1
                continue
            analysis = analyses.get(answer.id)
            analysis_data = serialize(analysis) if analysis else None
            if analysis and str(analysis.run_id) not in analysis_runs:
                analysis_runs[str(analysis.run_id)] = serialize(db.get(AnalysisRun, analysis.run_id))
            diagnoses = db.scalars(select(Diagnosis).where(Diagnosis.project_id == project['id'],
                Diagnosis.answer_id == answer.id, Diagnosis.analysis_id == analysis.id).limit(8)).all() if analysis else []
            sources = snapshot.get('sources', [])
            batch_answers.append({'answer_id': answer.id, 'batch_id': batch.id,
                'question_version_id': answer.question_version_id, 'question': q,
                'platform': answer.platform, 'observed_at': observed, 'text': answer.text,
                'analysis_id': analysis.id if analysis else None, 'analysis_version': analysis.version if analysis else None,
                'analysis': analysis_data, 'analysis_run_id': analysis.run_id if analysis else None,
                'diagnoses': [serialize(d) for d in diagnoses], 'sources': answer.sources,
                'source_state': answer.source_state, 'observation_time_provenance': answer.raw.get('_geo_observation_time'),
                'conditions': {'batch_mode': batch.mode, 'region': snapshot.get('region', ''),
                    'sampling': snapshot.get('sampling', {}), 'sources': sources,
                    'channel': 'unknown', 'source_modes': sorted({s.get('mode', 'unknown') for s in sources})}})
        if batch_answers:
            selected_batches.append({'id': batch.id, 'created_at': serialize(batch)['created_at'], 'mode': batch.mode})
            answers.extend(batch_answers)
    # Conditions are kept verbatim: supported research is evidence, not an algorithm law.
    research = []
    for item in db.scalars(select(Research).where(Research.project_id == project['id'], Research.status == 'supported').order_by(Research.id.desc()).limit(20)):
        if not item.reviewer.strip() or not item.review_note.strip() or parse_time(item.updated_at) < cutoff:
            continue
        revision = db.scalar(select(ResearchRevision).where(ResearchRevision.research_id == item.id).order_by(ResearchRevision.id.desc()).limit(1))
        if not revision:
            continue
        frozen = revision.snapshot
        current = serialize(item)
        if any(frozen.get('after', {}).get(k) != v for k, v in current.items() if k not in {'created_at', 'updated_at'}):
            continue
        verified = [e for e in frozen.get('evidence_snapshot', []) if e.get('verification') != 'operator_provided']
        if not verified or len(str(verified)) > 60000:
            continue
        research.append({**current, 'revision_id': revision.id, 'verified_evidence': verified,
                         'application': 'conditional_reference_only; conditions not automatically established'})
        if len(research) == 4:
            break
    rules = []
    research_ids = {r['id'] for r in research}
    for rule in db.scalars(select(OperationRule).where(OperationRule.project_id == project['id']).order_by(OperationRule.id.desc()).limit(20)):
        if not rule.reviewer.strip() or parse_time(rule.created_at) < cutoff:
            continue
        valid = True
        for key, model in [('research', Research), ('experiment', Experiment)]:
            identifier = getattr(rule, key + '_id')
            if identifier is None:
                continue
            source = db.get(model, identifier)
            frozen = rule.source_snapshot.get(key, {})
            if not source or source.project_id != project['id'] or source.status != 'supported':
                valid = False
                break
            current = serialize(source)
            if any(frozen.get(k) != v for k, v in current.items() if k not in {'created_at', 'updated_at'}):
                valid = False
                break
            if key == 'research' and identifier not in research_ids:
                valid = False
        if valid and len(str(rule.source_snapshot)) <= 60000:
            rules.append({**serialize(rule), 'application': 'conditional_reference_only; never a universal validated rule'})
        if len(rules) == 4:
            break
    return {'mode': 'answer_evidence' if answers else 'website_hypothesis', 'answers': answers,
        'batches': selected_batches, 'analysis_runs': analysis_runs, 'research': research, 'rules': rules,
        'selection': {'policy': 'latest six project batches, exact project brand/region, approved question IDs when supplied; latest analysis version frozen per answer; no merged ranks',
            'max_batches': MAX_BATCHES, 'max_answers': MAX_ANSWERS, 'max_answer_characters': MAX_TEXT,
            'max_age_days': MAX_AGE_DAYS, 'max_research': 4, 'max_rules': 4, 'excluded': excluded,
            'limitations': 'Bounded sample, not exhaustive; unmeasured demand, recommendation and algorithm preferences remain unknown. Research conditions are not automatically satisfied.'}}

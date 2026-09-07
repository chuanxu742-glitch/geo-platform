import copy
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import monitoring, research
from backend.app.analytics import analyze_batch
from backend.app.db import get_db
from backend.app.models import (Analysis, Answer, Base, Batch, Content, ContentVersion,
                                Page, PageSnapshot, Project, PublicationJob,
                                PublicationVerification, Question, QuestionVersion)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    engine = create_engine("sqlite:///" + (tmp_path / "research.db").as_posix(), connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(research.router, prefix="/api")
    app.include_router(monitoring.router, prefix="/api")

    def database():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, sessions
    engine.dispose()


def request(api, method, path, data=None, status=200):
    result = api[0].request(method, "/api" + path, json=data)
    assert result.status_code == status, result.text
    return result.json()


def seed(api, count=30, effect=True, controls=True):
    with api[1]() as db:
        project = Project(name="Research", brand="Alpha", website_url="https://example.org/page")
        db.add(project)
        db.flush()
        page = Page(project_id=project.id, url=project.website_url, title="Service")
        content = Content(project_id=project.id, title="Service", target_url=project.website_url)
        db.add_all([page, content])
        db.flush()
        version = ContentVersion(content_id=content.id, version=1, after_text="Approved service", fact_ids=[], facts_snapshot=[])
        db.add(version)
        db.flush()
        job = PublicationJob(project_id=project.id, content_version_id=version.id, page_id=page.id, source_kind="external_record", status="verified", target_url=page.url, expected_hash="a" * 64, execution_evidence={"operator_reported_at": "2026-09-03T00:00:00+00:00", "system_issued_write": False}, created_at=datetime(2026, 9, 3, tzinfo=timezone.utc), verified_at="2026-09-04T00:00:00+00:00")
        snapshot = PageSnapshot(page_id=page.id, source_kind="http", requested_url=page.url, final_url=page.url, http_status=200, status="success", visible_text=version.after_text)
        db.add_all([job, snapshot])
        db.flush()
        db.add(PublicationVerification(publication_job_id=job.id, snapshot_id=snapshot.id, status="verified", matched_by="visible_body", summary="Approved full body observed", verified_at=datetime(2026, 9, 4, tzinfo=timezone.utc)))
        questions = []
        for text in ("Target", "Control"):
            question = Question(project_id=project.id)
            db.add(question)
            db.flush()
            qv = QuestionVersion(question_id=question.id, version=1, text=text, branded=False)
            db.add(qv)
            db.flush()
            questions.append({"id": qv.id, "question_id": question.id, "text": text, "branded": False, "region": "", "intent": ""})
        snapshot = {"questions": questions, "sampling": {"platforms": ["manual"]}, "sources": [], "brand": "Alpha", "aliases": [], "competitors": [], "facts": []}
        control_ids = [questions[1]["question_id"]] if controls else []
        baseline = Batch(project_id=project.id, name="Baseline", mode="manual", snapshot=snapshot, control_question_ids=control_ids)
        db.add(baseline)
        db.flush()
        retest = Batch(project_id=project.id, name="Retest", mode="manual", snapshot=copy.deepcopy(snapshot), baseline_batch_id=baseline.id, content_version_ids=[version.id], control_question_ids=control_ids)
        db.add(retest)
        db.flush()
        answer_id = None
        for batch in (baseline, retest):
            for index, question in enumerate(questions):
                for _ in range(count):
                    answer = Answer(batch_id=batch.id, question_version_id=question["id"], platform="manual", text="Alpha is available" if batch == retest and index == 0 and effect else "No brand present", task_status="completed", validity="valid", complete=True, source_state="unknown", observed_at="2026-09-02T12:00:00+00:00" if batch == baseline else "2026-09-05T12:00:00+00:00")
                    db.add(answer)
                    db.flush()
                    if answer_id is None:
                        answer_id = answer.id
        db.commit()
        analyze_batch(db, baseline, False)
        analyze_batch(db, retest, False)
        return {"project": project.id, "page": page.id, "version": version.id, "baseline": baseline.id, "retest": retest.id, "answer": answer_id, "control": questions[1]["question_id"]}


def research_data(**changes):
    return {"platform": "manual", "channel": "web", "mode": "manual", "scenario": "service", "source_type": "answer", "claim": "Observed scoped claim, not algorithm mastery", "status": "hypothesis", "conditions": "Only sampled question and platform", "limitations": "Operator samples are not independent population estimates", "evidence": [], "reviewer": "Reviewer", "review_note": "Checked exact evidence", **changes}


def experiment_data(ids, **changes):
    return {"title": "Scoped mention comparison", "hypothesis": "Mentions may increase", "primary_change": "Clarify service copy", "page_id": ids["page"], "content_version_id": ids["version"], "baseline_batch_id": ids["baseline"], "retest_batch_id": ids["retest"], "window_start": "2026-09-01T00:00:00Z", "window_end": "2026-09-06T00:00:00Z", "metric": "mention_rate", "direction": "increase", "conditions": "Same frozen questions and platform", "limitations": "Descriptive only; repeated answers may be correlated", **changes}


def rule_data(**changes):
    return {"title": "Scoped rule", "instruction": "Use reviewed evidence", "conditions": "Sampled scenario only", "limitations": "Does not guarantee other platforms", "reviewer": "Reviewer", "review_note": "Reviewed source and scope", **changes}


def test_research_requires_verified_evidence_and_preserves_revision_provenance(api):
    ids = seed(api, count=1)
    path = f'/projects/{ids["project"]}/research'
    evidence = {"url": "https://example.org/source", "quote": "No brand present"}
    request(api, "POST", path, research_data(status="supported", evidence=[evidence]), 422)
    obj = request(api, "POST", path, research_data(evidence=[evidence]), 201)
    request(api, "PATCH", f'/research/{obj["id"]}', {"status": "supported"}, 422)
    evidence["answer_id"] = ids["answer"]
    request(api, "PATCH", f'/research/{obj["id"]}', {"status": "supported", "evidence": [evidence]})
    detail = request(api, "GET", f'/research/{obj["id"]}')
    assert [r["snapshot"]["after"]["status"] for r in detail["revisions"]] == ["hypothesis", "supported"]
    assert detail["revisions"][1]["snapshot"]["before"]["status"] == "hypothesis"
    assert detail["revisions"][1]["snapshot"]["evidence_snapshot"][0]["answer"]["text"] == "No brand present"
    rule = request(api, "POST", f'/projects/{ids["project"]}/operations/rules', rule_data(research_id=obj["id"]), 201)
    request(api, "PATCH", f'/research/{obj["id"]}', {"claim": "Revised hypothesis", "status": "hypothesis"})
    stored = request(api, "GET", f'/projects/{ids["project"]}/operations/rules')[0]
    assert stored["source_snapshot"] == rule["source_snapshot"]
    assert stored["source_snapshot"]["research"]["claim"] == obj["claim"]
    request(api, "POST", f'/projects/{ids["project"]}/operations/rules', rule_data(research_id=obj["id"]), 422)


@pytest.mark.parametrize("failure", ["wrong_quote", "invalid_answer", "foreign_answer", "credentials", "unsupported_status", "missing_review"])
def test_research_rejects_invalid_sources_and_review_bypass(api, failure):
    ids = seed(api, count=1)
    evidence = {"url": "https://example.org/source", "quote": "No brand present", "answer_id": ids["answer"]}
    data = research_data(status="supported", evidence=[evidence])
    if failure == "wrong_quote":
        evidence["quote"] = "Invented quote"
    elif failure == "invalid_answer":
        with api[1]() as db:
            db.get(Answer, ids["answer"]).validity = "invalid"
            db.commit()
    elif failure == "foreign_answer":
        evidence["answer_id"] = seed(api, count=1)["answer"]
    elif failure == "credentials":
        evidence["url"] = "https://user:password@example.org/source"
    elif failure == "unsupported_status":
        data["status"] = "validated"
    else:
        data["reviewer"] = " "
    request(api, "POST", f'/projects/{ids["project"]}/research', data, 422)


def test_http_snapshot_evidence_is_exact_and_not_manual_import(api):
    ids = seed(api, count=1)
    with api[1]() as db:
        snapshot = PageSnapshot(page_id=ids["page"], source_kind="manual_import", requested_url="https://example.org/page", final_url="https://example.org/page", http_status=200, status="success", visible_text="Observed page wording")
        db.add(snapshot)
        db.commit()
        snapshot_id = snapshot.id
    evidence = {"url": "https://example.org/page", "quote": "Observed page wording", "snapshot_id": snapshot_id}
    path = f'/projects/{ids["project"]}/research'
    request(api, "POST", path, research_data(status="supported", evidence=[evidence]), 422)
    with api[1]() as db:
        db.get(PageSnapshot, snapshot_id).source_kind = "http"
        db.commit()
    obj = request(api, "POST", path, research_data(status="supported", evidence=[evidence]), 201)
    assert request(api, "GET", f'/research/{obj["id"]}')["revisions"][0]["snapshot"]["evidence_snapshot"][0]["verification"] == "verified_http_snapshot"
    evidence["quote"] = "Invented"
    request(api, "POST", path, research_data(status="supported", evidence=[evidence]), 422)


@pytest.mark.parametrize("failure", ["foreign_page", "wrong_page", "wrong_retest", "wrong_version", "naive_window", "backwards_window", "outside_observation", "missing_observation", "changed_control"])
def test_experiment_rejects_invalid_associations_and_observation_windows(api, failure):
    ids = seed(api, count=1)
    data = experiment_data(ids)
    with api[1]() as db:
        if failure == "foreign_page":
            data["page_id"] = seed(api, count=1)["page"]
        elif failure == "wrong_page":
            db.get(Page, ids["page"]).url = "https://example.org/other"
        elif failure == "wrong_retest":
            db.get(Batch, ids["retest"]).baseline_batch_id = None
        elif failure == "wrong_version":
            db.get(Batch, ids["retest"]).content_version_ids = []
        elif failure == "naive_window":
            data["window_start"] = "2026-09-01T00:00:00"
        elif failure == "backwards_window":
            data["window_start"] = "2026-09-07T00:00:00Z"
        elif failure == "outside_observation":
            data["window_end"] = "2026-09-02T00:00:00Z"
        elif failure == "missing_observation":
            db.get(Answer, ids["answer"]).observed_at = None
        else:
            db.get(ContentVersion, ids["version"]).generation = {"question_ids": [ids["control"]]}
        db.commit()
    request(api, "POST", f'/projects/{ids["project"]}/experiments', data, 422)


def test_frozen_experiment_support_and_rule_survive_reanalysis(api):
    ids = seed(api)
    obj = request(api, "POST", f'/projects/{ids["project"]}/experiments', experiment_data(ids), 201)
    assert obj["conclusion_gate"]["supported"] == []
    assert obj["conclusion_gate"]["refuted"]
    with api[1]() as db:
        project = db.get(Project, ids["project"])
        project.aliases = ["No brand"]
        db.commit()
        analyze_batch(db, db.get(Batch, ids["baseline"]), False, True)
        analyze_batch(db, db.get(Batch, ids["retest"]), False, True)
    assert request(api, "GET", f'/experiments/{obj["id"]}')["comparison"] == obj["comparison"]
    result = request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "supported", "reviewer": "Reviewer", "note": "Descriptive positive difference only"})
    assert result["status"] == "supported" and result["reviewed_at"]
    assert result["analysis_run_ids"] == obj["analysis_run_ids"]
    rule = request(api, "POST", f'/projects/{ids["project"]}/operations/rules', rule_data(experiment_id=obj["id"]), 201)
    assert rule["source_snapshot"]["experiment"]["comparison"] == obj["comparison"]
    request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "refuted", "reviewer": "Other", "note": "Cannot rewrite history"}, 409)


@pytest.mark.parametrize("failure", ["small_sample", "no_control", "no_effect", "other_metric", "opposite_direction", "analysis_basis", "valid_coverage", "control_only", "unverified_publication"])
def test_conclusion_cannot_promote_unsupported_comparisons(api, failure):
    ids = seed(api, count=1 if failure == "small_sample" else 30, controls=failure != "no_control", effect=failure != "no_effect")
    data = experiment_data(ids)
    if failure == "other_metric":
        data["metric"] = "recommendation_rate"
    elif failure == "opposite_direction":
        data["direction"] = "decrease"
    elif failure == "unverified_publication":
        with api[1]() as db:
            db.query(PublicationJob).filter_by(content_version_id=ids["version"]).one().status = "awaiting_verification"
            db.commit()
    elif failure in ("analysis_basis", "valid_coverage", "control_only"):
        with api[1]() as db:
            if failure == "analysis_basis":
                db.get(Project, ids["project"]).aliases = ["No brand"]
                db.commit()
                analyze_batch(db, db.get(Batch, ids["baseline"]), False, True)
            elif failure == "valid_coverage":
                baseline = db.get(Batch, ids["baseline"])
                target = baseline.snapshot["questions"][0]["id"]
                for answer in db.query(Answer).filter_by(batch_id=baseline.id, question_version_id=target):
                    answer.validity = "unknown"
            else:
                baseline, retest = db.get(Batch, ids["baseline"]), db.get(Batch, ids["retest"])
                baseline.control_question_ids = retest.control_question_ids = [q["question_id"] for q in baseline.snapshot["questions"]]
            db.commit()
    obj = request(api, "POST", f'/projects/{ids["project"]}/experiments', data, 201)
    assert obj["conclusion_gate"]["supported"]
    request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "supported", "reviewer": "Reviewer", "note": "Manual choice cannot bypass gate"}, 422)
    if failure == "no_effect":
        request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "refuted", "reviewer": "Reviewer", "note": "Non-significance is not refutation"}, 422)
    result = request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "inconclusive", "reviewer": "Reviewer", "note": "Evidence cannot support a directional conclusion"})
    assert result["status"] == "inconclusive"
    request(api, "POST", f'/projects/{ids["project"]}/operations/rules', rule_data(experiment_id=obj["id"]), 422)


def test_refuted_requires_real_opposite_direction_and_review(api):
    ids = seed(api)
    obj = request(api, "POST", f'/projects/{ids["project"]}/experiments', experiment_data(ids, direction="decrease"), 201)
    request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "refuted", "reviewer": " ", "note": "Review"}, 422)
    result = request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "refuted", "reviewer": "Reviewer", "note": "Observed increase opposes hypothesized decrease"})
    assert result["status"] == "refuted"
    request(api, "POST", f'/projects/{ids["project"]}/operations/rules', rule_data(), 422)


@pytest.mark.parametrize("metric,direction", [("mention_rate", "increase"), ("recommendation_rate", "increase"), ("factual_error_rate", "decrease")])
def test_metric_intervals_use_known_samples_without_arbitrary_count_gate(api, metric, direction):
    ids = seed(api, count=20)
    with api[1]() as db:
        for batch_id in (ids["baseline"], ids["retest"]):
            batch = db.get(Batch, batch_id)
            target_version_id = batch.snapshot["questions"][0]["id"]
            for question in batch.snapshot["questions"]:
                answers = db.query(Answer).filter_by(batch_id=batch_id, question_version_id=question["id"]).order_by(Answer.id).all()
                for index, answer in enumerate(answers):
                    analysis = db.query(Analysis).filter_by(answer_id=answer.id).one()
                    treatment = question["id"] == target_version_id
                    positive = treatment and batch_id == ids["retest"]
                    analysis.recommendation = "recommended" if positive else "neutral"
                    analysis.factual_status = "consistent" if positive else "inconsistent"
                    if index >= 10:
                        analysis.brand_mentioned = None
                        analysis.recommendation = "unknown"
                        analysis.factual_status = "unknown"
        db.commit()
    obj = request(api, "POST", f'/projects/{ids["project"]}/experiments', experiment_data(ids, metric=metric, direction=direction), 201)
    target = obj["comparison"]["treatment_groups"][0]
    denominator = {"mention_rate": "mention_denominator", "recommendation_rate": "recommendation_denominator", "factual_error_rate": "factual_denominator"}[metric]
    assert target["baseline"][denominator] == target["retest"][denominator] == 10
    assert target["baseline"]["sample_count"] == target["retest"]["sample_count"] == 20
    assert obj["conclusion_gate"]["supported"] == []
    result = request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "supported", "reviewer": "Reviewer", "note": "Known sample interval is directional; small correlated samples remain a limitation"})
    assert result["status"] == "supported"


@pytest.fixture
def source_server(monkeypatch):
    state = {"requests": 0, "status": 200, "body": "<html><head><title>Research reference</title></head><body>Published evidence 中文.<span hidden>Hidden claim</span></body></html>"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):
            state["requests"] += 1
            body = state["body"].encode("utf-8")
            self.send_response(state["status"])
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("GEO_HTTP_ALLOWLIST", f"127.0.0.1:{server.server_port}")
    state["url"] = f"http://127.0.0.1:{server.server_port}/reference"
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


def test_research_source_fetch_offsets_and_historical_provenance(api, source_server):
    ids = seed(api, count=1)
    base = f'/projects/{ids["project"]}'
    source = request(api, "POST", base + "/research-sources/fetch", {"url": source_server["url"]}, 201)
    assert source["status"] == "success"
    assert source["title"] == "Research reference"
    assert source["visible_text"] == "Published evidence 中文."
    evidence = {"url": source_server["url"], "quote": "evidence 中文", "research_source_id": source["id"]}
    obj = request(api, "POST", base + "/research", research_data(status="supported", evidence=[evidence]), 201)
    saved = obj["evidence"][0]
    assert source["visible_text"][saved["start"]:saved["end"]] == evidence["quote"]
    rule = request(api, "POST", base + "/operations/rules", rule_data(research_id=obj["id"]), 201)
    source_server["body"] = "<title>Changed reference</title><p>Retracted observation</p>"
    changed = request(api, "POST", base + "/research-sources/fetch", {"url": source_server["url"]}, 201)
    assert changed["id"] != source["id"] and changed["visible_text"] == "Retracted observation"
    sources = request(api, "GET", base + "/research-sources")
    assert sources == [source, changed]
    assert source_server["requests"] == 2
    assert request(api, "GET", base + "/operations/rules")[0]["source_snapshot"] == rule["source_snapshot"]
    original = rule["source_snapshot"]["research"]["revisions"][0]["snapshot"]["evidence_snapshot"][0]["research_source"]
    assert original == source
    request(api, "POST", base + "/research", research_data(status="supported", evidence=[{**evidence, "start": 0, "end": len(evidence["quote"])}]), 422)
    request(api, "POST", base + "/research", research_data(status="supported", evidence=[{**evidence, "quote": "Hidden claim"}]), 422)
    other = seed(api, count=1)
    request(api, "POST", f'/projects/{other["project"]}/research', research_data(status="supported", evidence=[evidence]), 422)


def test_failed_research_source_is_saved_but_cannot_support_claim(api, source_server):
    ids = seed(api, count=1)
    source_server["status"] = 503
    base = f'/projects/{ids["project"]}'
    source = request(api, "POST", base + "/research-sources/fetch", {"url": source_server["url"]}, 201)
    assert source["status"] == "failure" and source["http_status"] == 503
    assert source["visible_text"] == source["content_hash"] == ""
    evidence = {"url": source_server["url"], "quote": "Published evidence", "research_source_id": source["id"]}
    request(api, "POST", base + "/research", research_data(status="supported", evidence=[evidence]), 422)
    assert request(api, "GET", base + "/research-sources") == [source]
    assert source_server["requests"] == 1


@pytest.mark.parametrize("timeline", ["both_after_publication", "reversed_batches", "before_verification", "missing_operator_time", "reversed_publication"])
def test_experiment_cannot_conclude_without_real_before_after_intervention(api, timeline):
    ids = seed(api)
    with api[1]() as db:
        job = db.query(PublicationJob).filter_by(content_version_id=ids["version"]).one()
        if timeline == "missing_operator_time":
            job.execution_evidence = {"system_issued_write": False}
        elif timeline == "reversed_publication":
            job.execution_evidence = {"operator_reported_at": "2026-09-05T00:00:00+00:00"}
        else:
            for answer in db.query(Answer).filter(Answer.batch_id.in_([ids["baseline"], ids["retest"]])):
                if timeline == "both_after_publication":
                    answer.observed_at = "2026-09-05T12:00:00+00:00" if answer.batch_id == ids["baseline"] else "2026-09-05T13:00:00+00:00"
                elif timeline == "reversed_batches":
                    answer.observed_at = "2026-09-05T12:00:00+00:00" if answer.batch_id == ids["baseline"] else "2026-09-02T12:00:00+00:00"
                elif answer.batch_id == ids["retest"]:
                    answer.observed_at = "2026-09-03T12:00:00+00:00"
        db.commit()
    obj = request(api, "POST", f'/projects/{ids["project"]}/experiments', experiment_data(ids), 201)
    assert obj["conclusion_gate"]["supported"]
    request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "supported", "reviewer": "Reviewer", "note": "Direction alone cannot prove before/after timing"}, 422)
    result = request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "inconclusive", "reviewer": "Reviewer", "note": "Intervention timing cannot establish a baseline then retest"})
    assert result["status"] == "inconclusive"


def test_wordpress_intervention_uses_job_start_and_first_visible_verification(api):
    ids = seed(api)
    with api[1]() as db:
        job = db.query(PublicationJob).filter_by(content_version_id=ids["version"]).one()
        job.source_kind = "wordpress"
        job.execution_evidence = {"submission": {"http_status": 200, "observed_at": "2026-09-03T01:00:00+00:00"}}
        first = db.query(PublicationVerification).filter_by(publication_job_id=job.id).one()
        db.add(PublicationVerification(publication_job_id=job.id, snapshot_id=first.snapshot_id, status="verified", matched_by="visible_body", summary="Later verification", verified_at=datetime(2026, 9, 6, tzinfo=timezone.utc)))
        db.commit()
    obj = request(api, "POST", f'/projects/{ids["project"]}/experiments', experiment_data(ids), 201)
    timeline = obj["comparison"]["publication_timeline"]
    assert timeline["start"] == "2026-09-03T00:00:00+00:00"
    assert timeline["end"] == "2026-09-04T00:00:00+00:00"
    result = request(api, "POST", f'/experiments/{obj["id"]}/conclude', {"status": "supported", "reviewer": "Reviewer", "note": "Baseline predates actual submission; retest follows first verified visibility"})
    assert result["status"] == "supported"

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app import main
from backend.app.db import get_db
from backend.app.models import Base
from backend.app.integrations import validity, record_answer


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "RAZORMIND_URL", "GEO_BACKEND_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    engine = create_engine("sqlite:///" + (tmp_path / "test.db").as_posix(), connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main.agent_runtime, "Session", sessions)
    def database():
        with sessions() as db:
            yield db
    monkeypatch.setattr(main, "migrate", lambda: None)
    main.app.dependency_overrides[get_db] = database
    with TestClient(main.app) as api:
        yield api
    main.app.dependency_overrides.clear()
    engine.dispose()


def call(client, method, path, data=None, code=200):
    response = client.request(method, "/api" + path, json=data)
    assert response.status_code == code, response.text
    return response.json()


def project_batch(client, controls=False):
    p = call(client, "POST", "/projects", {"name": "测试", "brand": "Alpha", "aliases": ["阿尔法"]}, 201)
    q = call(client, "POST", f'/projects/{p["id"]}/questions', {"text": "Alpha如何选择", "branded": False, "region": "中国", "intent": "购买"}, 201)
    b = call(client, "POST", f'/projects/{p["id"]}/batches', {"name": "基线", "question_ids": [q["id"]], "sampling": {"platforms": ["测试平台"]}, "control_question_ids": [q["id"]] if controls else []}, 201)
    return p, q, b


def imported(client, batch, question, text, **kwargs):
    return call(client, "POST", f'/batches/{batch["id"]}/import', {"answers": [{"question_version_id": question["current_version"]["id"], "platform": "测试平台", "text": text, "validity": "valid", "complete": True, **kwargs}]}, 201)[0]


@pytest.fixture
def remote(monkeypatch):
    state = {"triggers": [], "statuses": {}, "records": {}, "gets": [], "model": {}, "model_inputs": [], "trigger_error": False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return
        def send_json(self, data, status=200):
            raw = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if self.path == "/api/v1/tasks/trigger":
                state["triggers"].append(body)
                if state["trigger_error"]:
                    self.send_json({"detail": "ambiguous"}, 503)
                else:
                    self.send_json({"success": True, "data": {"task_id": str(len(state["triggers"]))}}, 202)
            elif self.path == "/v1/chat/completions":
                state["model_inputs"].append(body)
                assert body["response_format"] == {"type": "json_object"}
                self.send_json({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(state["model"])}}]})
            else:
                self.send_json({"detail": "missing"}, 404)
        def do_GET(self):
            from urllib.parse import urlsplit, parse_qs
            state["gets"].append(self.path)
            if self.path.startswith("/api/v1/records"):
                params = parse_qs(urlsplit(self.path).query)
                task_id = params["task_id"][0]
                page = int(params["page"][0])
                items = state["records"].get(task_id, [])
                self.send_json({"data": items[page-1:page], "meta": {"page": page, "total": len(items), "total_pages": len(items)}})
            elif self.path.endswith("/runs"):
                self.send_json({"data": [{"id": "run1", "result": {"api_token": "hidden"}}]})
            else:
                task_id = self.path.split("/")[-1]
                self.send_json({"data": {"id": task_id, "status": state["statuses"].get(task_id, "pending"), "result": {"Authorization": "Bearer secret-probe"}}})
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("RAZORMIND_URL", url)
    monkeypatch.setenv("OPENAI_BASE_URL", url + "/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-not-real")
    monkeypatch.setenv("OPENAI_MODEL", "protocol-test-not-real")
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


def test_reanalysis_and_question_snapshot(client):
    p, q, b = project_batch(client)
    answer = imported(client, b, q, "  客观正文，没有目标品牌。\n")
    assert answer["text"] == "  客观正文，没有目标品牌。\n"
    for _ in range(2):
        call(client, "POST", f'/batches/{b["id"]}/analyze', {})
    overview = call(client, "GET", f'/projects/{p["id"]}/overview')
    group = overview["groups"][0]
    assert (group["sample_count"], group["mention_denominator"], group["brand_mentions"]) == (1, 1, 0)
    assert group["recommendation_rate"] is None and group["recommendation_unknown_count"] == 1
    call(client, "PATCH", f'/questions/{q["id"]}', {"text": "已修改"})
    call(client, "PATCH", f'/projects/{p["id"]}', {"brand": "Changed", "aliases": ["Other"]})
    call(client, "DELETE", f'/questions/{q["id"]}')
    assert call(client, "GET", f'/batches/{b["id"]}')["snapshot"] == b["snapshot"]
    detail = call(client, "GET", f'/answers/{answer["id"]}')
    assert len(detail["analyses"]) == 2
    assert detail["analyses"][1]["input_snapshot"]["brand"] == "Alpha"


def test_invalid_unknown_and_sources_denominators(client):
    p, q, b = project_batch(client)
    imported(client, b, q, "Alpha", sources=[])
    imported(client, b, q, "Alpha", complete=False)
    imported(client, b, q, "[NO RESPONSE]", sources=[])
    imported(client, b, q, "正文 https://example.org/page")
    call(client, "POST", f'/batches/{b["id"]}/analyze', {})
    g = call(client, "GET", f'/projects/{p["id"]}/overview')["groups"][0]
    assert (g["sample_count"], g["valid_count"], g["invalid_count"], g["unknown_count"]) == (4, 2, 1, 1)
    assert g["source_known_count"] == 1
    assert g["metrics"]["sources"]["answer_ids"] == []
    assert g["factual_denominator"] == 0 and g["factual_unknown_count"] == 4


@pytest.mark.parametrize("text,role,expected", [
    ("No response within 60s...", "", "invalid"),
    ("[NO RESPONSE]", "", "invalid"),
    ("超时提示", "System", "invalid"),
    ("Alpha是问题中的品牌", "User", "invalid"),
    ("[NO RESPONSE]\n这个标记说明上游无输出，以下解释其含义。", "Assistant", "valid"),
])
def test_collector_error_markers_and_roles(text, role, expected):
    assert validity(text, "completed", "valid", True, role)[0] == expected


def test_missing_role_and_role_arrays():
    source = {"platform": "test", "answer_complete": True, "result_mapping": {"text": "raw_data.rows"}}
    answer = record_answer({"raw_data": {"rows": [{"Role": "User", "Text": "Alpha?"}, {"Role": "Assistant", "Text": "正文没有品牌"}]}}, source)
    assert answer["text"] == "正文没有品牌" and answer["validity"] == "valid"
    source["result_mapping"] = {"text": "raw_data.Text", "role": "raw_data.Role"}
    assert record_answer({"raw_data": {"Text": "Alpha"}}, source)["validity"] == "unknown"


def test_retest_inherits_controls_and_requires_coverage(client):
    p, q, b = project_batch(client, controls=True)
    imported(client, b, q, "Alpha")
    r = call(client, "POST", f'/projects/{p["id"]}/batches', {"name": "复测", "baseline_batch_id": b["id"]}, 201)
    assert r["control_question_ids"] == [q["id"]]
    assert call(client, "GET", f'/batches/{r["id"]}/compare')["comparable"] is False
    call(client, "POST", f'/batches/{r["id"]}/import', {"answers": [{"question_version_id": q["current_version"]["id"], "platform": "其他平台", "text": "x"}]}, 422)
    imported(client, r, q, "Alpha")
    comparison = call(client, "GET", f'/batches/{r["id"]}/compare')
    assert comparison["comparable"] is True and comparison["control_groups"][0]["retest"]["sample_count"] == 1
    call(client, "POST", f'/projects/{p["id"]}/batches', {"name": "不匹配", "baseline_batch_id": b["id"], "sampling": {"platforms": ["其他平台"]}}, 422)


def collection_batch(client, count=1):
    p = call(client, "POST", "/projects", {"name": "采集", "brand": "Alpha"}, 201)
    q = call(client, "POST", f'/projects/{p["id"]}/questions', {"text": "原始问题", "branded": False}, 201)
    sources = [call(client, "POST", f'/projects/{p["id"]}/sources', {"name": str(i), "platform": "源平台", "source_id": "source-" + str(i), "parameter_mapping": {"question": "text"}, "answer_complete": True}, 201) for i in range(count)]
    b = call(client, "POST", f'/projects/{p["id"]}/batches', {"name": "采集基线", "question_ids": [q["id"]], "source_ids": [s["id"] for s in sources]}, 201)
    return p, q, b, sources


def test_source_snapshot_trigger_once_poll_and_pagination(client, remote):
    p, q, b, sources = collection_batch(client)
    call(client, "PATCH", f'/sources/{sources[0]["id"]}', {"source_id": "changed", "parameter_mapping": {"question": "question"}})
    jobs = call(client, "POST", f'/batches/{b["id"]}/collect')["jobs"]
    call(client, "POST", f'/batches/{b["id"]}/collect')
    assert len(remote["triggers"]) == 1
    assert remote["triggers"][0]["parameters"] == {"text": "原始问题"}
    assert remote["triggers"][0]["source_id"] == "source-0"
    remote["statuses"]["1"] = "awaiting_confirm"
    waiting = call(client, "POST", f'/batches/{b["id"]}/sync')
    assert waiting["status"] == "awaiting_confirm" and waiting["imported"] == 0
    assert not any("records" in path for path in remote["gets"])
    assert "secret-probe" not in json.dumps(waiting)
    remote["statuses"]["1"] = "completed"
    remote["records"]["1"] = [{"id": str(i), "task_id": "1", "normalized_data": {"response": "Alpha"}, "lineage": {"workflow_run_id": "run1"}} for i in range(2)]
    remote["records"]["1"][0]["normalized_data"]["observed_at"] = "2020-01-01T00:00:00Z"
    result = call(client, "POST", f'/batches/{b["id"]}/sync')
    assert result["imported"] == 2 and result["status"] == "completed"
    assert call(client, "POST", f'/batches/{b["id"]}/sync')["imported"] == 0
    detail = call(client, "GET", f'/batches/{b["id"]}')
    assert len(detail["answers"]) == 2 and detail["answers"][0]["raw"]["lineage"]["workflow_run_id"] == "run1"
    assert detail["answers"][0]["observed_at"] == "2020-01-01T00:00:00+00:00"
    assert detail["answers"][0]["raw"]["_geo_observation_time"]["basis"] == "provided_observation"
    assert detail["answers"][1]["observed_at"] is not None
    assert detail["answers"][1]["raw"]["_geo_observation_time"]["basis"] == "server_received"


def test_uncertain_submission_never_retriggered(client, remote):
    _, _, b, _ = collection_batch(client)
    remote["trigger_error"] = True
    first = call(client, "POST", f'/batches/{b["id"]}/collect')
    assert first["jobs"][0]["status"] == "submission_unknown"
    call(client, "POST", f'/batches/{b["id"]}/collect')
    assert len(remote["triggers"]) == 1


def test_sync_rollback_count_and_mixed_terminal_status(client, remote):
    _, _, b, _ = collection_batch(client, count=2)
    call(client, "POST", f'/batches/{b["id"]}/collect')
    remote["statuses"].update({"1": "completed", "2": "failed"})
    remote["records"]["1"] = [{"id": "a", "task_id": "1", "normalized_data": {"response": "Alpha"}}, {"id": "b", "task_id": "wrong", "normalized_data": {"response": "Alpha"}}]
    result = call(client, "POST", f'/batches/{b["id"]}/sync')
    assert result["imported"] == 0
    assert call(client, "GET", f'/batches/{b["id"]}')["answers"] == []
    remote["records"]["1"] = remote["records"]["1"][:1]
    result = call(client, "POST", f'/batches/{b["id"]}/sync')
    assert result["status"] == "partial_failed" and result["failed_count"] == 1 and result["imported"] == 1


def semantic(text, recommendation="neutral", list_evidence=False):
    evidence = {"start": 0, "end": len(text), "quote": text}
    return {"recommendation": recommendation, "recommendation_evidence": [evidence], "recommendation_list_evidence": [evidence] if list_evidence else [], "factual_findings": [], "competitor_recommendations": []}


@pytest.mark.parametrize("text,recommendation,list_evidence,rank", [
    ("1. 不要选择Alpha\n2. 可选Beta", "not_recommended", False, None),
    ("1. 联系Alpha\n2. 付款", "neutral", False, None),
    ("推荐清单：\n1. Alpha\n2. Beta", "recommended", True, 1),
])
def test_rank_requires_semantic_recommendation_list(client, remote, text, recommendation, list_evidence, rank):
    p, q, b = project_batch(client)
    a = imported(client, b, q, text)
    remote["model"] = semantic(text, recommendation, list_evidence)
    call(client, "POST", f'/batches/{b["id"]}/analyze', {"use_model": True})
    detail = call(client, "GET", f'/answers/{a["id"]}')
    assert detail["analyses"][0]["rank"] == rank
    group = call(client, "GET", f'/projects/{p["id"]}/overview')["groups"][0]
    assert group["recommendation_denominator"] == 1
    assert group["neutral_count"] == (1 if recommendation == "neutral" else 0)


def test_model_quote_unicode_validation_is_atomic(client, remote):
    _, q, b = project_batch(client)
    a = imported(client, b, q, "😀推荐Alpha")
    remote["model"] = semantic(a["text"], "recommended")
    remote["model"]["recommendation_evidence"] = [{"start": 1, "end": 8, "quote": "推荐Alpha"}]
    call(client, "POST", f'/batches/{b["id"]}/analyze', {"use_model": True})
    remote["model"]["recommendation_evidence"][0]["start"] = 2
    call(client, "POST", f'/batches/{b["id"]}/analyze', {"use_model": True}, 502)
    assert len(call(client, "GET", f'/answers/{a["id"]}')["analyses"]) == 1


def test_fact_validity_window_and_archive_history(client, remote):
    p, q, _ = project_batch(client)
    fact = call(client, "POST", f'/projects/{p["id"]}/facts', {"claim": "保修三年", "source_url": "https://example.org", "valid_from": "2020-01-01T00:00:00Z", "valid_to": "2021-01-01T00:00:00Z"}, 201)
    b = call(client, "POST", f'/projects/{p["id"]}/batches', {"name": "时间窗口", "question_ids": [q["id"]], "sampling": {"platforms": ["测试平台"]}}, 201)
    a = imported(client, b, q, "Alpha保修一年", observed_at="2021-01-01T00:00:00Z")
    remote["model"] = semantic(a["text"])
    remote["model"]["factual_findings"] = [{"fact_id": fact["id"], "status": "inconsistent", "evidence": {"start": 0, "end": len(a["text"]), "quote": a["text"]}, "explanation": "不符"}]
    call(client, "POST", f'/batches/{b["id"]}/analyze', {"use_model": True}, 502)
    assert call(client, "GET", f'/answers/{a["id"]}')["analyses"] == []
    call(client, "DELETE", f'/facts/{fact["id"]}')
    assert call(client, "GET", f'/batches/{b["id"]}')["snapshot"]["facts"][0]["claim"] == "保修三年"


def test_no_model_does_not_generate_fake_content(client):
    p, _, _ = project_batch(client)
    fact = call(client, "POST", f'/projects/{p["id"]}/facts', {"claim": "保修三年", "source_url": "https://example.org"}, 201)
    content = call(client, "POST", f'/projects/{p["id"]}/contents', {"title": "指南"}, 201)
    call(client, "POST", f'/contents/{content["id"]}/generate', {"instructions": "改写", "fact_ids": [fact["id"]]}, 503)
    assert call(client, "GET", f'/projects/{p["id"]}/contents')[0]["versions"] == []


def test_active_fact_mismatch_is_traceable(client, remote):
    p, q, _ = project_batch(client)
    fact = call(client, "POST", f'/projects/{p["id"]}/facts', {"claim": "保修三年", "source_url": "https://example.org", "valid_from": "2020-01-01T00:00:00Z", "valid_to": "2021-01-01T00:00:00Z"}, 201)
    b = call(client, "POST", f'/projects/{p["id"]}/batches', {"name": "有效时间", "question_ids": [q["id"]], "sampling": {"platforms": ["测试平台"]}}, 201)
    a = imported(client, b, q, "Alpha保修一年", observed_at="2020-01-01T00:00:00Z")
    remote["model"] = semantic(a["text"])
    remote["model"]["factual_findings"] = [{"fact_id": fact["id"], "status": "inconsistent", "evidence": {"start": 0, "end": len(a["text"]), "quote": a["text"]}, "explanation": "一年与三年不符"}]
    call(client, "POST", f'/batches/{b["id"]}/analyze', {"use_model": True})
    group = call(client, "GET", f'/projects/{p["id"]}/overview?batch_id={b["id"]}')["groups"][0]
    assert group["factual_error_rate"] == 1 and group["metrics"]["factual"]["answer_ids"] == [a["id"]]
    diagnoses = call(client, "POST", f'/batches/{b["id"]}/diagnose')
    mismatch = next(item for item in diagnoses if item["kind"] == "fact_mismatch")
    assert mismatch["evidence"]["facts"][0]["source_url"] == fact["source_url"]


def test_real_http_content_draft_validation_and_publication(client, remote, monkeypatch):
    from operations_peer import controlled_peer
    with controlled_peer() as (url, site):
        monkeypatch.setenv("GEO_HTTP_ALLOWLIST", url.split("//")[1])
        p, _, _ = project_batch(client)
        call(client, "PATCH", f'/projects/{p["id"]}', {"website_url": url})
        page = call(client, "POST", f'/projects/{p["id"]}/pages', {"url": url + "/service"}, 201)
        fact = call(client, "POST", f'/projects/{p["id"]}/facts', {"claim": "保修三年", "source_url": "https://example.org"}, 201)
        content = call(client, "POST", f'/projects/{p["id"]}/contents', {"title": "指南", "target_url": page["url"]}, 201)
        remote["model"] = {"text": "保修三年", "used_fact_ids": [fact["id"]], "factual_claims": [{"fact_id": fact["id"], "start": 0, "end": 4, "quote": "保修三年"}]}
        draft = call(client, "POST", f'/contents/{content["id"]}/generate', {"instructions": "据此写简短说明", "fact_ids": [fact["id"]]}, 201)
        assert draft["after_text"] == "保修三年" and draft["generation"]["review_required"] is True
        call(client, "POST", f'/content-versions/{draft["id"]}/external-publication', {"page_id": page["id"], "note": "外部操作记录"}, 409)
        call(client, "POST", f'/content-versions/{draft["id"]}/review', {"status": "approved", "reviewer": "内容负责人", "note": "逐条核对事实"})
        published = call(client, "POST", f'/content-versions/{draft["id"]}/external-publication', {"page_id": page["id"], "note": "外部操作记录"}, 201)
        assert published["source_kind"] == "external_record" and published["status"] == "awaiting_verification"
        site["body"] = draft["after_text"]
        verified = call(client, "POST", f'/publication-jobs/{published["id"]}/verify')
        assert verified["status"] == "verified"
        remote["model"]["factual_claims"][0]["quote"] = "捏造"
        call(client, "POST", f'/contents/{content["id"]}/generate', {"instructions": "据此写简短说明", "fact_ids": [fact["id"]]}, 502)
        assert len(call(client, "GET", f'/projects/{p["id"]}/contents')[0]["versions"]) == 1


def test_citation_url_required_and_invalid_fact_default_is_422(client):
    p, q, b = project_batch(client)
    call(client, "POST", f'/batches/{b["id"]}/import', {"answers": [{"question_version_id": q["current_version"]["id"], "platform": "测试平台", "text": "Alpha", "sources": [{"title": "缺URL"}]}]}, 422)
    call(client, "POST", f'/projects/{p["id"]}/facts', {"claim": "历史事实", "source_url": "https://example.org", "valid_to": "2020-01-01T00:00:00Z"}, 422)


def test_explicit_alias_reanalysis_preserves_history_and_comparison_basis(client):
    p, q, b = project_batch(client)
    a = imported(client, b, q, "新简称提供服务")
    call(client, "POST", f'/batches/{b["id"]}/analyze', {})
    original = call(client, "GET", f'/answers/{a["id"]}')["analyses"][0]
    assert original["brand_mentioned"] is False
    call(client, "PATCH", f'/projects/{p["id"]}', {"aliases": ["新简称"]})
    call(client, "POST", f'/batches/{b["id"]}/analyze', {})
    assert call(client, "GET", f'/answers/{a["id"]}')["analyses"][-1]["brand_mentioned"] is False
    call(client, "POST", f'/batches/{b["id"]}/analyze', {"use_current_aliases": True})
    detail = call(client, "GET", f'/answers/{a["id"]}')
    assert detail["analyses"][-1]["brand_mentioned"] is True
    assert detail["analyses"][-1]["input_snapshot"]["aliases"] == ["新简称"]
    assert detail["analyses"][-1]["input_snapshot"]["alias_policy"] == "current_project"
    assert detail["analyses"][0] == original
    assert detail["text"] == a["text"]
    assert call(client, "GET", f'/batches/{b["id"]}')["snapshot"] == b["snapshot"]
    group = call(client, "GET", f'/projects/{p["id"]}/overview?batch_id={b["id"]}')["groups"][0]
    assert (group["sample_count"], group["mention_denominator"], group["brand_mentions"]) == (1, 1, 1)
    r = call(client, "POST", f'/projects/{p["id"]}/batches', {"name": "复测", "baseline_batch_id": b["id"]}, 201)
    imported(client, r, q, "新简称提供服务")
    call(client, "POST", f'/batches/{r["id"]}/analyze', {})
    comparison = call(client, "GET", f'/batches/{r["id"]}/compare')
    assert comparison["analysis_basis_match"] is False and comparison["comparable"] is False
    call(client, "POST", f'/batches/{r["id"]}/analyze', {"use_current_aliases": True})
    assert call(client, "GET", f'/batches/{r["id"]}/compare')["analysis_basis_match"] is True
    call(client, "PATCH", f'/projects/{p["id"]}', {"aliases": ["不匹配的新别名"]})
    call(client, "POST", f'/batches/{b["id"]}/analyze', {"use_current_aliases": True})
    diagnoses = call(client, "POST", f'/batches/{b["id"]}/diagnose')
    absence = next(item for item in diagnoses if item["kind"] == "brand_absent")
    assert absence["evidence"]["aliases"] == ["不匹配的新别名"]
    assert absence["evidence"]["alias_policy"] == "current_project"


def test_new_import_defaults_observation_to_receipt_without_rewriting_history(client):
    from datetime import datetime, timezone
    p, q, batch = project_batch(client)
    before = datetime.now(timezone.utc)
    defaults = [imported(client, batch, q, "完整新观测", **options) for options in ({}, {"observed_at": None})]
    after = datetime.now(timezone.utc)
    for answer in defaults:
        assert before <= datetime.fromisoformat(answer["observed_at"]) <= after
        assert answer["raw"]["_geo_observation_time"]["basis"] == "server_received"
    historical = imported(client, batch, q, "过去的完整观测", observed_at="2020-01-01T00:00:00Z")
    call(client, "POST", f'/batches/{batch["id"]}/analyze', {})
    unchanged = call(client, "GET", f'/answers/{historical["id"]}')
    assert unchanged["observed_at"] == "2020-01-01T00:00:00+00:00"
    assert unchanged["raw"]["_geo_observation_time"]["basis"] == "provided_observation"

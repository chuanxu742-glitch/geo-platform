import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
import pytest
from test_contract import client, call
from operations_peer import controlled_peer


@pytest.fixture
def wp(client, monkeypatch):
    with controlled_peer() as (url, state):
        monkeypatch.setenv("GEO_HTTP_ALLOWLIST", url.split("//")[1])
        monkeypatch.setenv("WORDPRESS_URL", url)
        monkeypatch.setenv("WORDPRESS_USERNAME", "controlled-operator")
        monkeypatch.setenv("WORDPRESS_APPLICATION_PASSWORD", "controlled-application-password")
        p = call(client, "POST", "/projects", {"name": "运营回归", "brand": "Alpha", "website_url": url}, 201)
        page = call(client, "POST", f'/projects/{p["id"]}/pages', {"url": url + "/service", "owner": "编辑"}, 201)
        q = call(client, "POST", f'/projects/{p["id"]}/questions', {"text": "服务包括什么？", "branded": False}, 201)
        fact = call(client, "POST", f'/projects/{p["id"]}/facts', {"claim": "提供安装服务", "source_url": page["url"]}, 201)
        content = call(client, "POST", f'/projects/{p["id"]}/contents', {"title": "服务说明", "target_url": page["url"]}, 201)
        version = call(client, "POST", f'/contents/{content["id"]}/versions', {"after_text": "<p>Alpha 提供安装服务，服务区域由订单确认。</p>", "fact_ids": [fact["id"]]}, 201)
        publisher = call(client, "POST", f'/projects/{p["id"]}/publishers', {"name": "受控WP", "site_url": url, "post_id": 17}, 201)
        yield {"project": p, "page": page, "question": q, "fact": fact, "content": content, "version": version, "publisher": publisher, "state": state, "url": url}


def approve(client, wp):
    return call(client, "POST", f'/content-versions/{wp["version"]["id"]}/review', {"status": "approved", "reviewer": "编辑", "note": "核对官网事实"})


def submit(client, wp, code=201):
    return call(client, "POST", f'/content-versions/{wp["version"]["id"]}/publish-jobs', {"publisher_id": wp["publisher"]["id"], "page_id": wp["page"]["id"]}, code)


def test_approval_and_fact_edit_gate_all_publication_paths(client, wp):
    submit(client, wp, 409)
    call(client, "POST", f'/content-versions/{wp["version"]["id"]}/external-publication', {"page_id": wp["page"]["id"], "note": "人工声明"}, 409)
    approve(client, wp)
    call(client, "PATCH", f'/facts/{wp["fact"]["id"]}', {"claim": "已停止安装服务"})
    submit(client, wp, 422)
    assert wp["state"]["posts"] == []
    assert call(client, "GET", f'/projects/{wp["project"]["id"]}/publication-jobs') == []


def test_wordpress_writes_once_then_visible_body_verification(client, wp):
    approve(client, wp)
    before = call(client, "GET", f'/projects/{wp["project"]["id"]}/operations/summary')
    assert [v["id"] for v in before["ready_to_publish"]] == [wp["version"]["id"]]
    job = submit(client, wp)
    assert job["status"] == "awaiting_verification" and job["verified_at"] is None
    again = submit(client, wp, 200)
    assert again["id"] == job["id"] and len(wp["state"]["posts"]) == 1
    assert wp["state"]["posts"][0]["content"] == wp["version"]["after_text"]
    summary = call(client, "GET", f'/projects/{wp["project"]["id"]}/operations/summary')
    assert [j["id"] for j in summary["awaiting_verification"]] == [job["id"]]
    verified = call(client, "POST", f'/publication-jobs/{job["id"]}/verify')
    assert verified["status"] == "verified" and verified["verifications"][-1]["matched_by"] == "visible_body"
    assert len(wp["state"]["posts"]) == 1
    call(client, "POST", f'/content-versions/{wp["version"]["id"]}/review', {"status": "rejected", "reviewer": "编辑", "note": "改稿应新建版本"}, 409)


@pytest.mark.parametrize("mode", ["hidden", "script"])
def test_hidden_approved_body_never_verifies(client, wp, mode):
    approve(client, wp)
    job = submit(client, wp)
    wp["state"]["mode"] = mode
    failed = call(client, "POST", f'/publication-jobs/{job["id"]}/verify')
    assert failed["status"] == "verification_failed" and failed["verified_at"] is None
    wp["state"]["mode"] = "normal"
    recovered = call(client, "POST", f'/publication-jobs/{job["id"]}/verify')
    assert recovered["status"] == "verified" and len(recovered["verifications"]) == 2
    assert len(wp["state"]["posts"]) == 1


def test_wrong_resource_link_prevents_write(client, wp):
    approve(client, wp)
    wp["state"]["link_path"] = "/other"
    submit(client, wp, 422)
    assert wp["state"]["posts"] == []


def test_unknown_submission_never_reposts_and_can_verify(client, wp):
    approve(client, wp)
    wp["state"]["mode"] = "unknown"
    job = submit(client, wp)
    assert job["status"] == "submission_unknown"
    assert submit(client, wp, 200)["id"] == job["id"]
    result = call(client, "POST", f'/publication-jobs/{job["id"]}/verify')
    assert result["status"] == "verified" and len(wp["state"]["posts"]) == 1


def test_auth_failure_is_not_publication_success(client, wp):
    approve(client, wp)
    wp["state"]["mode"] = "auth_error"
    job = submit(client, wp)
    assert job["status"] == "execution_failed" and job["verified_at"] is None
    assert wp["state"]["posts"] == []
    assert submit(client, wp, 200)["status"] == "execution_failed"


def test_missing_credentials_and_wrong_server_base_do_not_leak_or_write(client, wp, monkeypatch):
    approve(client, wp)
    monkeypatch.delenv("WORDPRESS_APPLICATION_PASSWORD")
    submit(client, wp, 503)
    monkeypatch.setenv("WORDPRESS_APPLICATION_PASSWORD", "controlled-application-password")
    monkeypatch.setenv("WORDPRESS_URL", "https://other.invalid")
    submit(client, wp, 503)
    assert wp["state"]["posts"] == []


def test_external_declaration_does_not_qualify_retest_until_verified(client, wp):
    approve(client, wp)
    q, p = wp["question"], wp["project"]
    baseline = call(client, "POST", f'/projects/{p["id"]}/batches', {"name": "固定基线", "question_ids": [q["id"]], "sampling": {"platforms": ["人工观测"]}}, 201)
    call(client, "POST", f'/batches/{baseline["id"]}/import', {"answers": [{"question_version_id": q["current_version"]["id"], "platform": "人工观测", "text": "原始观测", "complete": True, "validity": "valid"}]}, 201)
    job = call(client, "POST", f'/content-versions/{wp["version"]["id"]}/external-publication', {"page_id": wp["page"]["id"], "note": "人工已外发，等待GET核验"}, 201)
    payload = {"name": "复测", "baseline_batch_id": baseline["id"], "content_version_ids": [wp["version"]["id"]]}
    call(client, "POST", f'/projects/{p["id"]}/batches', payload, 422)
    wp["state"]["body"] = wp["version"]["after_text"]
    call(client, "POST", f'/publication-jobs/{job["id"]}/verify')
    retest = call(client, "POST", f'/projects/{p["id"]}/batches', payload, 201)
    assert retest["content_version_ids"] == [wp["version"]["id"]] and wp["state"]["posts"] == []


def test_check_due_performs_read_and_deduplicates_maintenance_action(client, wp):
    approve(client, wp)
    job = submit(client, wp)
    call(client, "POST", f'/publication-jobs/{job["id"]}/verify')
    call(client, "PATCH", f'/pages/{wp["page"]["id"]}', {"next_review_at": "2020-01-01T00:00:00Z"})
    first = call(client, "POST", f'/projects/{wp["project"]["id"]}/operations/check-due')
    assert first["checked"][0]["status"] == "verified"
    action = first["actions"][0]
    assert action["owner"] == "编辑" and action["page_id"] == wp["page"]["id"]
    call(client, "PATCH", f'/pages/{wp["page"]["id"]}', {"next_review_at": "2020-01-01T00:00:00Z"})
    second = call(client, "POST", f'/projects/{wp["project"]["id"]}/operations/check-due')
    assert second["actions"][0]["id"] == action["id"] and len(wp["state"]["posts"]) == 1


def test_initial_database_upgrade_preserves_real_history(tmp_path):
    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "legacy.db"
    environment = {**os.environ, "DATABASE_URL": "sqlite:///" + database.as_posix()}
    def migrate(revision):
        result = subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", revision], cwd=root, env=environment, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    migrate("2e4666322eb1")
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO projects VALUES (1,'用户项目','用户品牌','[\"别名\"]','https://example.org','中国','2025-01-01')")
        db.execute("INSERT INTO actions VALUES (1,1,'用户行动','[]','https://example.org','[]','[]','编辑','done','人工验收','2025-01-01')")
        db.execute("INSERT INTO contents VALUES (1,1,'用户页面','https://example.org',1,'2025-01-01')")
        db.execute("INSERT INTO content_versions VALUES (1,1,1,'旧稿','保留用户原稿','[]','[]','{}','2025-01-02T00:00:00Z','2025-01-01')")
    migrate("head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT name,aliases FROM projects").fetchone() == ("用户项目", '["别名"]')
        assert db.execute("SELECT after_text,published_at,review_status FROM content_versions").fetchone() == ("保留用户原稿", "2025-01-02T00:00:00Z", "pending")
        assert db.execute("SELECT title,status,blocked_reason FROM actions").fetchone() == ("用户行动", "done", "")
        assert db.execute("SELECT count(*) FROM publication_jobs").fetchone()[0] == 0
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

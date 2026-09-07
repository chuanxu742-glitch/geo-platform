"""Measurement API tests use only a temporary SQLite database, with no app startup."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import sessionmaker

from backend.app import measurement
from backend.app.db import get_db
from backend.app.measurement_models import Measurement
from backend.app.models import Project


@pytest.fixture
def api(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "measurement-test.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "backend/alembic.ini"))
    config.set_main_option("script_location", str(root / "backend/migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "b82e4c65f901")
    engine = create_engine(url, connect_args={"check_same_thread": False})
    session = sessionmaker(engine, expire_on_commit=False)
    with session() as db:
        db.add_all([Project(name="One", brand="One"), Project(name="Two", brand="Two")])
        db.commit()

    def database():
        with session() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    app = FastAPI()
    app.include_router(measurement.router, prefix="/api")
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, session, engine, config
    engine.dispose()


def row(**changes):
    return {"date": "2026-09-07", "page_url": "https://example.com/page", "channel": "seo",
            "impressions": 100, "clicks": 7, "leads": None, "orders": None, **changes}


def upload(api, rows, project=1, source="Search export"):
    return api[0].post(f"/api/projects/{project}/measurements/import",
                       json={"source_label": source, "rows": rows})


def read(api, project=1):
    return api[0].get(f"/api/projects/{project}/measurements")


def test_unknown_zero_and_provenance(api):
    empty = read(api).json()
    assert empty["rows"] == []
    assert empty["summary"] == dict.fromkeys(measurement.METRICS)
    assert upload(api, [row(orders=0)]).json()["imported"] == 1
    result = read(api).json()
    assert result["summary"] == {"impressions": 100, "clicks": 7, "leads": None, "orders": 0}
    record = result["rows"][0]
    assert record["query"] == ""
    assert record["source_kind"] == "manual_import"
    assert record["source_label"] == "Search export"
    assert record["imported_at"] and record["project_id"] == 1
    assert result["limitations"]
    assert upload(api, [row(date="2026-09-06", impressions=None, orders=None, leads=2)]).status_code == 200
    assert read(api).json()["summary"] == {"impressions": None, "clicks": 14, "leads": None, "orders": None}


def test_repeat_and_in_batch_duplicates_preserve_original_provenance(api):
    result = upload(api, [row(), row()]).json()
    assert result == {"imported": 1, "duplicates": 1, "source_label": "Search export"}
    original = read(api).json()
    assert upload(api, [row()]).json()["duplicates"] == 1
    assert read(api).json() == original
    assert upload(api, [row(), row(query="different")]).json()["imported"] == 1
    assert len(read(api).json()["rows"]) == 2


def test_project_isolation_and_missing_projects(api):
    upload(api, [row()])
    assert read(api, 2).json()["rows"] == []
    assert upload(api, [row()], project=2).json()["imported"] == 1
    assert read(api).json()["rows"][0]["id"] != read(api, 2).json()["rows"][0]["id"]
    assert upload(api, [row()], project=999).status_code == 404
    assert read(api, 999).status_code == 404


def test_conflicting_metrics_in_batch_reject_every_row(api):
    assert upload(api, [row(query="separate"), row(), row(clicks=8)]).status_code == 409
    assert read(api).json()["rows"] == []


def test_conflicting_existing_identity_rejects_every_new_row(api):
    upload(api, [row()])
    original = read(api).json()
    assert upload(api, [row(query="new"), row(leads=0)]).status_code == 409
    assert read(api).json() == original


def test_summary_overflow_stays_unknown(api):
    maximum = 9_007_199_254_740_991
    upload(api, [row(query="one", impressions=maximum), row(query="two", impressions=1)])
    result = read(api).json()
    assert result["summary"]["impressions"] is None
    assert result["summary"]["clicks"] == 14
    assert any("安全整数" in limitation for limitation in result["limitations"])


@pytest.mark.parametrize("changes", [
    {"date": "2026-02-30"}, {"date": "2026-9-07"}, {"date": "2026-09-07T00:00:00"},
    {"page_url": "javascript:alert(1)"}, {"page_url": "https://"},
    {"page_url": "https://user:pass@example.com"}, {"page_url": "https://exa mple.com"},
    {"page_url": "/relative"}, {"page_url": "http:example.com"},
    {"channel": "paid"}, {"query": "a" * 2001}, {"impressions": -1},
    {"clicks": True}, {"leads": 1.5}, {"orders": "2"}, {"orders": 2**63},
    {"project_id": 2},
])
def test_invalid_row_rejects_entire_batch(api, changes):
    assert upload(api, [row(query="valid first"), row(**changes)]).status_code == 422
    assert read(api).json()["rows"] == []


def test_bounded_payload_and_blank_source(api):
    assert upload(api, []).status_code == 422
    assert upload(api, [row()] * 1001).status_code == 422
    assert upload(api, [row()], source="   ").status_code == 422
    assert upload(api, [row()], source="a" * 201).status_code == 422
    assert read(api).json()["rows"] == []
    assert upload(api, [row(query=str(i)) for i in range(1000)]).json()["imported"] == 1000
    assert upload(api, [row(query=str(i)) for i in range(1000)]).json()["duplicates"] == 1000


def test_missing_metrics_stay_unknown_and_distinct_sources_are_retained(api):
    minimal = {"date": "2024-02-29", "page_url": "http://example.com", "channel": "geo"}
    assert upload(api, [minimal]).status_code == 200
    assert read(api).json()["summary"] == dict.fromkeys(measurement.METRICS)
    assert upload(api, [minimal], source="Another export").json()["imported"] == 1
    assert len(read(api).json()["rows"]) == 2


def test_database_failure_rolls_back_whole_import(api):
    engine = api[2]
    inserts = []

    def fail_second(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO measurements"):
            inserts.append(statement)
            if len(inserts) == 2:
                raise RuntimeError("Injected storage failure")

    event.listen(engine, "before_cursor_execute", fail_second)
    try:
        with pytest.raises(RuntimeError, match="Injected storage failure"):
            upload(api, [row(query="first"), row(query="second")])
    finally:
        event.remove(engine, "before_cursor_execute", fail_second)
    with api[1]() as db:
        assert list(db.scalars(select(Measurement))) == []


def test_additive_migration_round_trip(api):
    command.downgrade(api[3], "a71d9b33e204")
    assert "measurements" not in inspect(api[2]).get_table_names()
    with api[1]() as db:
        assert db.get(Project, 1).name == "One"
    command.upgrade(api[3], "b82e4c65f901")
    assert "measurements" in inspect(api[2]).get_table_names()

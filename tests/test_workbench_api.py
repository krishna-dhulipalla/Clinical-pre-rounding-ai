from datetime import timedelta
from time import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from workbench.api import create_app
from workbench.config import Settings
from workbench.demo import DEMO_CLOCK
from workbench.persistence import Database, RunRow, SnapshotRow

HEADERS = {"X-Workbench-Request": "1"}


@pytest.fixture
def v2_client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'wb.db').as_posix()}",
        public_url="http://testserver",
        embedded_worker=False,
    )
    database = Database(settings.database_url)
    app = create_app(settings, database)
    with TestClient(app) as client:
        assert client.post("/api/session/demo", headers=HEADERS).status_code == 200
        yield client
    database.engine.dispose()


def payload(patient="demo-avery", scenario="normal"):
    return {
        "patient_id": patient,
        "encounter_id": patient.replace("demo-", "enc-"),
        "window_start": (DEMO_CLOCK - timedelta(hours=36)).isoformat(),
        "since": (DEMO_CLOCK - timedelta(hours=14)).isoformat(),
        "as_of": DEMO_CLOCK.isoformat(),
        "scenario": scenario,
    }


def enqueue(client, body=None, key=None):
    return client.post(
        "/api/runs", json=body or payload(), headers={**HEADERS, "Idempotency-Key": key or str(uuid4())}
    )


def finished(client, body=None):
    response = enqueue(client, body)
    assert response.status_code == 202, response.text
    client.app.state.worker.run_once()
    detail = client.get("/api/runs/" + response.json()["id"])
    assert detail.status_code == 200, detail.text
    return detail.json()


def test_end_to_end_evidence_review_and_revision_conflict(v2_client):
    data = finished(v2_client)
    assert data["status"] == "completed", data
    snapshot = data["snapshot"]
    assert "resources" not in snapshot
    evidence_id = snapshot["claims"][0]["evidence_ids"][0]
    source = v2_client.get(f"/api/runs/{data['id']}/evidence/{evidence_id}")
    assert source.json()["resource"]["resourceType"] == "Observation"
    assert source.headers["cache-control"] == "no-store"
    review = {
        "expected_revision": 0,
        "selected_claim_ids": [c["id"] for c in snapshot["claims"]],
        "note": "Reviewed synthetic sources.",
        "accept": True,
    }
    result = v2_client.post(f"/api/runs/{data['id']}/reviews", json=review, headers=HEADERS)
    assert result.status_code == 200, result.text
    assert result.json()["review_status"] == "accepted"
    assert result.json()["reviews"][0]["snapshot_hash"] == snapshot["snapshot_hash"]
    assert result.json()["reviews"][0]["actor_id"] == "demo-clinician"
    assert v2_client.post(f"/api/runs/{data['id']}/reviews", json=review, headers=HEADERS).status_code == 409


def test_idempotency_reuses_jobs_and_rejects_changed_payload(v2_client):
    key = str(uuid4())
    first, second = enqueue(v2_client, key=key), enqueue(v2_client, key=key)
    assert first.json()["id"] == second.json()["id"]
    changed = enqueue(v2_client, payload("demo-jordan"), key)
    assert changed.status_code == 409
    assert len(v2_client.get("/api/runs").json()) == 1


def test_job_persists_across_new_worker_instance(v2_client):
    response = enqueue(v2_client)
    from workbench.worker import Worker

    old = v2_client.app.state.worker
    replacement = Worker(old.database, old.settings, old.auth)
    assert replacement.run_once()
    assert v2_client.get(f"/api/runs/{response.json()['id']}").json()["status"] == "completed"


def test_queued_and_running_cancellation_prevent_publishing(v2_client, monkeypatch):
    job = enqueue(v2_client).json()
    assert v2_client.post(f"/api/runs/{job['id']}/cancel", headers=HEADERS).status_code == 200
    assert not v2_client.app.state.worker.run_once()
    assert not v2_client.get(f"/api/runs/{job['id']}").json()["snapshot"]
    from workbench import worker as module

    original = module.build_snapshot
    job2 = enqueue(v2_client).json()

    def cancel_during_processing(source, request):
        result = original(source, request)
        assert v2_client.post(f"/api/runs/{job2['id']}/cancel", headers=HEADERS).status_code == 200
        return result

    monkeypatch.setattr(module, "build_snapshot", cancel_during_processing)
    v2_client.app.state.worker.run_once()
    result = v2_client.get(f"/api/runs/{job2['id']}").json()
    assert result["status"] == "cancelled" and result["snapshot"] is None


@pytest.mark.parametrize("scenario", ["outage", "denied"])
def test_incomplete_briefings_cannot_be_accepted(v2_client, scenario):
    data = finished(v2_client, payload(scenario=scenario))
    assert data["status"] == "abstained"
    result = v2_client.post(
        f"/api/runs/{data['id']}/reviews",
        headers=HEADERS,
        json={"expected_revision": 0, "selected_claim_ids": [], "accept": True},
    )
    assert result.status_code == 409


def test_cookie_csrf_and_logout(v2_client):
    assert v2_client.post("/api/session/demo").status_code == 403
    assert (
        v2_client.post("/api/session/demo", headers={**HEADERS, "Origin": "https://evil.example"}).status_code
        == 403
    )
    assert v2_client.post("/api/session/logout", headers=HEADERS).status_code == 200
    assert v2_client.get("/api/patients").status_code == 401


def test_patient_and_run_isolation(v2_client):
    result = finished(v2_client)
    token, _ = v2_client.app.state.auth.issue("other-clinician", "Other", ["demo-jordan"], 300)
    v2_client.cookies.set("wb_session", token)
    assert v2_client.get("/api/patients/demo-avery/encounters").status_code == 403
    assert v2_client.get(f"/api/runs/{result['id']}").status_code == 404
    assert enqueue(v2_client).status_code == 403
    assert v2_client.get("/api/runs").json() == []


def test_expired_session_fails_worker_and_cannot_be_used(v2_client):
    job = enqueue(v2_client).json()
    from workbench.persistence import SessionRow

    with v2_client.app.state.database.sessions.begin() as db:
        db.execute(update(SessionRow).values(expires_at=time() - 1))
    v2_client.app.state.worker.run_once()
    with v2_client.app.state.database.sessions() as db:
        assert db.get(RunRow, job["id"]).status == "failed"
        assert db.get(SnapshotRow, job["id"]) is None
    assert v2_client.get("/api/session").status_code == 401


def test_worker_lease_recovery_and_retry_limit(v2_client):
    job = enqueue(v2_client).json()
    database = v2_client.app.state.database
    with database.sessions.begin() as db:
        row = db.get(RunRow, job["id"])
        row.status, row.lease_until, row.lease_owner, row.attempts = "running", time() - 1, "dead-worker", 1
    assert v2_client.app.state.worker.run_once()
    assert v2_client.get(f"/api/runs/{job['id']}").json()["attempts"] == 2
    job = enqueue(v2_client).json()
    with database.sessions.begin() as db:
        row = db.get(RunRow, job["id"])
        row.status, row.lease_until, row.attempts = "running", time() - 1, 3
    v2_client.app.state.worker.run_once()
    assert v2_client.get(f"/api/runs/{job['id']}").json()["error_code"] == "retry_limit"


def test_review_cannot_invent_sources_or_silently_drop_claims(v2_client):
    data = finished(v2_client)
    url = f"/api/runs/{data['id']}/reviews"
    assert (
        v2_client.post(
            url, headers=HEADERS, json={"expected_revision": 0, "selected_claim_ids": ["invented"]}
        ).status_code
        == 422
    )
    assert (
        v2_client.post(
            url,
            headers=HEADERS,
            json={
                "expected_revision": 0,
                "selected_claim_ids": [data["snapshot"]["claims"][0]["id"]],
                "accept": True,
            },
        ).status_code
        == 422
    )


def test_evaluation_and_operational_metrics_expose_denominators(v2_client):
    finished(v2_client)
    report = v2_client.get("/api/evaluation").json()
    assert report["metrics"]["case_pass_rate"] == {"numerator": 5, "denominator": 5, "value": 1.0}
    operations = v2_client.get("/api/operations").json()
    assert operations["total_runs"] == 1 and operations["completed"] == 1
    assert any(event["action"] == "run.completed" for event in operations["events"])

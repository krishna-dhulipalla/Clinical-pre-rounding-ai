from time import time
from uuid import uuid4

from workbench.maintenance import purge
from workbench.persistence import AccessEvent, Database, ReviewRow, RunRow, SessionRow, SnapshotRow


def test_retention_previews_and_preserves_running_jobs(tmp_path):
    database = Database(f"sqlite:///{(tmp_path / 'retention.db').as_posix()}")
    database.migrate()
    old = time() - 100 * 86400
    ids = [str(uuid4()), str(uuid4())]
    with database.sessions.begin() as db:
        for index, status in enumerate(("completed", "running")):
            db.add(
                RunRow(
                    id=ids[index],
                    owner_id="demo-clinician",
                    patient_id="demo-avery",
                    encounter_id="enc-avery",
                    idempotency_key=str(uuid4()),
                    request_hash="hash",
                    request_json={},
                    status=status,
                    trace_id=str(uuid4()),
                    created_at=old,
                )
            )
        db.flush()
        db.add(SnapshotRow(run_id=ids[0], payload={}, fingerprint="hash"))
        db.add(
            ReviewRow(
                run_id=ids[0],
                revision=1,
                actor_id="demo-clinician",
                selected_claim_ids=[],
                note="",
                status="draft",
                snapshot_hash="hash",
            )
        )
        db.add(
            SessionRow(
                token_hash="expired",
                actor_id="demo-clinician",
                display_name="Demo",
                patient_ids=[],
                expires_at=time() - 1,
            )
        )
        db.add(
            AccessEvent(actor_id="demo-clinician", action="run.viewed", trace_id=str(uuid4()), created_at=old)
        )
    assert purge(database)["runs"] == 1
    with database.sessions() as db:
        assert db.get(RunRow, ids[0]) is not None
    assert purge(database, apply=True)["applied"]
    with database.sessions() as db:
        assert db.get(RunRow, ids[0]) is None
        assert db.get(SnapshotRow, ids[0]) is None
        assert db.get(RunRow, ids[1]) is not None
        assert db.query(AccessEvent).count() == 1
        assert db.get(SessionRow, "expired") is None
    database.engine.dispose()

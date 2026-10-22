import logging
import threading
from time import time, perf_counter
from uuid import uuid4

from sqlalchemy import and_, or_, select, update

from .domain import RunRequest
from .generation import rank_claims
from .persistence import AccessEvent, RunRow, SessionRow, SnapshotRow
from .pipeline import EvidenceIntegrityError, build_snapshot
from .security import Principal

logger = logging.getLogger("workbench.worker")


class Worker:
    def __init__(self, database, settings, auth):
        self.database, self.settings, self.auth = database, settings, auth
        self.id = str(uuid4())
        self.stop_event = threading.Event()
        self.last_poll = 0.0
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.loop, name="workbench-worker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def loop(self):
        while not self.stop_event.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.error("worker_poll_failed", extra={"worker_id": self.id})
                worked = False
            if not worked:
                self.stop_event.wait(0.5)

    def claim(self):
        now = time()
        with self.database.sessions.begin() as db:
            eligible = or_(
                RunRow.status == "queued", and_(RunRow.status == "running", RunRow.lease_until < now)
            )
            db.execute(
                update(RunRow)
                .where(eligible, RunRow.attempts >= 3)
                .values(status="failed", error_code="retry_limit", updated_at=now)
            )
            job_id = db.scalar(
                select(RunRow.id).where(eligible, RunRow.attempts < 3).order_by(RunRow.created_at).limit(1)
            )
            if not job_id:
                return None
            count = db.execute(
                update(RunRow)
                .where(RunRow.id == job_id, eligible, RunRow.attempts < 3)
                .values(
                    status="running",
                    attempts=RunRow.attempts + 1,
                    lease_owner=self.id,
                    lease_until=now + 300,
                    updated_at=now,
                )
            ).rowcount
            return job_id if count else None

    def run_once(self):
        self.last_poll = time()
        job_id = self.claim()
        if not job_id:
            return False
        heartbeat_stop = threading.Event()

        def renew_lease():
            while not heartbeat_stop.wait(10):
                self.last_poll = time()
                try:
                    with self.database.sessions.begin() as db:
                        count = db.execute(
                            update(RunRow)
                            .where(
                                RunRow.id == job_id, RunRow.status == "running", RunRow.lease_owner == self.id
                            )
                            .values(lease_until=time() + 300)
                        ).rowcount
                        if not count:
                            return
                except Exception:
                    logger.error("lease_renewal_failed", extra={"worker_id": self.id})

        heartbeat = threading.Thread(target=renew_lease, daemon=True)
        heartbeat.start()
        started = perf_counter()
        try:
            with self.database.sessions() as db:
                row = db.get(RunRow, job_id)
                if row.session_hash:
                    session = db.get(SessionRow, row.session_hash)
                    if not session or session.expires_at <= time():
                        raise PermissionError("Session expired")
                    principal = Principal(
                        session.actor_id,
                        session.display_name,
                        tuple(session.patient_ids),
                        session.token_hash,
                        session.encounter_id,
                    )
                else:
                    principal = Principal(
                        row.owner_id, "Configured service principal", self.settings.patient_ids
                    )
                if row.patient_id not in principal.patient_ids:
                    raise PermissionError("Patient scope changed")
                request = RunRequest.model_validate(row.request_json)
                trace_id = row.trace_id
            snapshot = build_snapshot(self.auth.source(principal), request)
            snapshot = rank_claims(snapshot, self.settings)
            snapshot.telemetry["total_ms"] = round((perf_counter() - started) * 1000, 2)
            status = "completed" if snapshot.complete and snapshot.claims else "abstained"
            with self.database.sessions.begin() as db:
                changed = db.execute(
                    update(RunRow)
                    .where(RunRow.id == job_id, RunRow.status == "running", RunRow.lease_owner == self.id)
                    .values(status=status, updated_at=time(), lease_until=None, error_code=None)
                ).rowcount
                if not changed:
                    return True  # Cancelled or reclaimed; discard this worker's result.
                db.add(
                    SnapshotRow(
                        run_id=job_id,
                        payload=snapshot.model_dump(mode="json"),
                        fingerprint=snapshot.snapshot_hash,
                    )
                )
                db.add(
                    AccessEvent(
                        actor_id=principal.actor_id,
                        action=f"run.{status}",
                        patient_id=request.patient_id,
                        run_id=job_id,
                        trace_id=trace_id,
                    )
                )
            logger.info(
                "run_finished",
                extra={
                    "trace_id": trace_id,
                    "job_status": status,
                    "duration_ms": snapshot.telemetry["total_ms"],
                },
            )
        except Exception as exc:
            permanent = isinstance(exc, (EvidenceIntegrityError, PermissionError, ValueError))
            with self.database.sessions.begin() as db:
                row = db.get(RunRow, job_id)
                if row.status == "running" and row.lease_owner == self.id:
                    row.status = "failed" if permanent or row.attempts >= 3 else "queued"
                    row.error_code = (
                        "evidence_integrity"
                        if isinstance(exc, EvidenceIntegrityError)
                        else "authorization_expired"
                        if isinstance(exc, PermissionError)
                        else "processing_failed"
                    )
                    row.lease_until, row.updated_at = None, time()
            logger.error(
                "run_failed",
                extra={"trace_id": getattr(row, "trace_id", ""), "failure_type": type(exc).__name__},
            )
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=2)
        return True


def main():
    from .logging import configure_logging

    configure_logging()
    from .config import Settings
    from .persistence import Database
    from .security import Auth

    settings = Settings.from_env()
    database = Database(settings.database_url)
    if not database.ready():
        raise RuntimeError("Migrate the database before starting the worker")
    worker = Worker(database, settings, Auth(database, settings))
    try:
        worker.loop()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    main()

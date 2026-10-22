from datetime import datetime, timezone
from time import time

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .domain import ReviewRequest, RunRequest, Snapshot, digest
from .persistence import AccessEvent, ReviewRow, RunRow, SnapshotRow
from .pipeline import EvidenceIntegrityError, verify_snapshot


class Conflict(ValueError):
    pass


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def run_dict(row):
    return {
        "id": row.id,
        "patient_id": row.patient_id,
        "encounter_id": row.encounter_id,
        "status": row.status,
        "attempts": row.attempts,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
        "revision": row.revision,
        "review_status": row.review_status,
        "error_code": row.error_code,
        "trace_id": row.trace_id,
        "request": row.request_json,
    }


class Workbench:
    def __init__(self, database, settings, auth):
        self.database, self.settings, self.auth = database, settings, auth

    def audit(self, principal, action, trace_id, patient_id=None, run_id=None, outcome="allowed"):
        with self.database.sessions.begin() as db:
            db.add(
                AccessEvent(
                    actor_id=principal.actor_id,
                    action=action,
                    trace_id=trace_id,
                    patient_id=patient_id,
                    run_id=run_id,
                    outcome=outcome,
                )
            )

    def authorize(self, principal, patient_id, trace_id):
        if patient_id not in principal.patient_ids:
            self.audit(principal, "patient.access", trace_id, patient_id=patient_id, outcome="denied")
            raise PermissionError("Patient is outside the authorized context")

    def owned(self, db, principal, run_id):
        row = db.get(RunRow, run_id)
        if not row or row.owner_id != principal.actor_id or row.patient_id not in principal.patient_ids:
            raise KeyError("Run not found")
        if principal.encounter_id and row.encounter_id != principal.encounter_id:
            raise KeyError("Run not found")
        return row

    def enqueue(self, principal, request: RunRequest, idempotency_key, trace_id):
        self.authorize(principal, request.patient_id, trace_id)
        if principal.encounter_id and request.encounter_id != principal.encounter_id:
            raise PermissionError("Encounter is outside the authorized launch context")
        if self.settings.mode != "demo" and request.scenario != "normal":
            raise ValueError("Failure simulation is only available with synthetic data")
        payload = request.model_dump(mode="json")
        fingerprint = digest(payload)
        with self.database.sessions() as db:
            existing = db.scalar(
                select(RunRow).where(
                    RunRow.owner_id == principal.actor_id, RunRow.idempotency_key == idempotency_key
                )
            )
            if existing:
                if existing.request_hash != fingerprint:
                    raise Conflict("Idempotency key was already used with another request")
                return run_dict(existing)
            row = RunRow(
                owner_id=principal.actor_id,
                session_hash=principal.session_hash,
                patient_id=request.patient_id,
                encounter_id=request.encounter_id,
                request_hash=fingerprint,
                request_json=payload,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
            )
            db.add(row)
            try:
                db.flush()
                db.add(
                    AccessEvent(
                        actor_id=principal.actor_id,
                        action="run.created",
                        patient_id=request.patient_id,
                        run_id=row.id,
                        trace_id=trace_id,
                    )
                )
                db.commit()
            except IntegrityError:
                db.rollback()
                existing = db.scalar(
                    select(RunRow).where(
                        RunRow.owner_id == principal.actor_id, RunRow.idempotency_key == idempotency_key
                    )
                )
                if not existing or existing.request_hash != fingerprint:
                    raise Conflict("Idempotency conflict")
                return run_dict(existing)
            return run_dict(row)

    def list_runs(self, principal):
        with self.database.sessions() as db:
            query = select(RunRow).where(
                RunRow.owner_id == principal.actor_id, RunRow.patient_id.in_(principal.patient_ids)
            )
            if principal.encounter_id:
                query = query.where(RunRow.encounter_id == principal.encounter_id)
            return [run_dict(row) for row in db.scalars(query.order_by(RunRow.created_at.desc()).limit(100))]

    def snapshot(self, db, row):
        record = db.get(SnapshotRow, row.id)
        if not record:
            return None
        snapshot = Snapshot.model_validate(record.payload)
        expected = digest(snapshot.model_dump(mode="json", exclude={"snapshot_hash", "telemetry", "engine"}))
        if record.fingerprint != expected or snapshot.snapshot_hash != expected:
            raise EvidenceIntegrityError("Stored evidence fingerprint mismatch")
        verify_snapshot(snapshot)
        return snapshot

    def detail(self, principal, run_id, trace_id):
        with self.database.sessions() as db:
            row = self.owned(db, principal, run_id)
            snapshot = self.snapshot(db, row)
            revisions = list(
                db.scalars(select(ReviewRow).where(ReviewRow.run_id == run_id).order_by(ReviewRow.revision))
            )
            result = run_dict(row)
            result["snapshot"] = snapshot.model_dump(mode="json", exclude={"resources"}) if snapshot else None
            result["reviews"] = [
                {
                    "revision": review.revision,
                    "actor_id": review.actor_id,
                    "note": review.note,
                    "note_origin": "clinician_authored_unverified",
                    "status": review.status,
                    "selected_claim_ids": review.selected_claim_ids,
                    "snapshot_hash": review.snapshot_hash,
                    "created_at": iso(review.created_at),
                }
                for review in revisions
            ]
        self.audit(principal, "run.viewed", trace_id, result["patient_id"], run_id)
        return result

    def evidence(self, principal, run_id, evidence_id, trace_id):
        with self.database.sessions() as db:
            row = self.owned(db, principal, run_id)
            snapshot = self.snapshot(db, row)
            fact = (
                next((f for f in snapshot.facts if f.evidence_id == evidence_id), None) if snapshot else None
            )
            if not fact:
                raise KeyError("Evidence not found")
            result = {
                "fact": fact.model_dump(mode="json"),
                "resource": snapshot.resources[fact.resource_key],
                "snapshot_hash": snapshot.snapshot_hash,
            }
            patient_id = row.patient_id
        self.audit(principal, "evidence.viewed", trace_id, patient_id, run_id)
        return result

    def review(self, principal, run_id, request: ReviewRequest, trace_id):
        with self.database.sessions.begin() as db:
            row = self.owned(db, principal, run_id)
            if row.status not in {"completed", "abstained"}:
                raise Conflict("Wait for the evidence snapshot before reviewing")
            snapshot = self.snapshot(db, row)
            allowed_ids = {claim.id for claim in snapshot.claims}
            selected = request.selected_claim_ids
            if len(set(selected)) != len(selected) or not set(selected).issubset(allowed_ids):
                raise ValueError("Review contains duplicate or unknown claim IDs")
            if request.accept and (not snapshot.complete or not selected):
                raise Conflict("An incomplete or empty briefing cannot be accepted")
            if len(allowed_ids) != len(selected) and request.accept and not request.note.strip():
                raise ValueError("Explain excluded claims in the clinician note before acceptance")
            revision = request.expected_revision + 1
            changed = db.execute(
                update(RunRow)
                .where(RunRow.id == run_id, RunRow.revision == request.expected_revision)
                .values(
                    revision=revision,
                    review_status="accepted" if request.accept else "draft",
                    updated_at=time(),
                )
            ).rowcount
            if not changed:
                raise Conflict("This draft changed in another session. Reload before saving")
            db.add(
                ReviewRow(
                    run_id=run_id,
                    revision=revision,
                    actor_id=principal.actor_id,
                    selected_claim_ids=selected,
                    note=request.note.strip(),
                    status="accepted" if request.accept else "draft",
                    snapshot_hash=snapshot.snapshot_hash,
                )
            )
            db.add(
                AccessEvent(
                    actor_id=principal.actor_id,
                    action="review.accepted" if request.accept else "review.saved",
                    patient_id=row.patient_id,
                    run_id=run_id,
                    trace_id=trace_id,
                )
            )
        return self.detail(principal, run_id, trace_id)

    def cancel(self, principal, run_id, trace_id):
        with self.database.sessions.begin() as db:
            row = self.owned(db, principal, run_id)
            count = db.execute(
                update(RunRow)
                .where(RunRow.id == run_id, RunRow.status.in_(["queued", "running"]))
                .values(status="cancelled", updated_at=time())
            ).rowcount
            if not count:
                raise Conflict("Only queued or running jobs can be cancelled")
            db.add(
                AccessEvent(
                    actor_id=principal.actor_id,
                    action="run.cancelled",
                    patient_id=row.patient_id,
                    run_id=run_id,
                    trace_id=trace_id,
                )
            )
        return {"id": run_id, "status": "cancelled"}

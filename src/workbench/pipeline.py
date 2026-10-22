from collections import defaultdict
from decimal import Decimal
from time import perf_counter

from fhir.client import FHIRRequestError
from .domain import Change, Claim, Coverage, CoverageState, RunRequest, Snapshot, digest
from .normalization import decimal_text, event_time, normalize_resource, resource_identity
from .sources import REQUIRED_TYPES, NOT_QUERIED, Source, matches_reference


class EvidenceIntegrityError(ValueError):
    pass


def check_subject(resource, request, base_url):
    subject = resource.get("subject", {}).get("reference", "")
    context_key = "context" if resource.get("resourceType") == "MedicationAdministration" else "encounter"
    encounter = resource.get(context_key, {}).get("reference", "")
    if not matches_reference(subject, "Patient", request.patient_id, base_url):
        raise EvidenceIntegrityError("Patient isolation check failed")
    if not matches_reference(encounter, "Encounter", request.encounter_id, base_url):
        return False
    return True


def calculate_changes(facts, since):
    groups = defaultdict(list)
    for fact in facts:
        if (
            fact.kind == "Observation"
            and fact.code
            and fact.code_system
            and fact.unit
            and fact.unit_system == "http://unitsofmeasure.org"
            and fact.numeric_value is not None
            and not fact.comparator
            and fact.timestamp
            and fact.date_precision == "instant"
        ):
            groups[(fact.code_system, fact.code, fact.unit)].append(fact)
    changes = []
    for group in groups.values():
        before = sorted((f for f in group if f.timestamp <= since), key=lambda f: f.timestamp)
        after = sorted((f for f in group if f.timestamp > since), key=lambda f: f.timestamp)
        if not before or not after:
            continue
        previous, current = before[-1], after[-1]
        # Two different resources at the same instant are ambiguous, not a trend.
        if (
            sum(f.timestamp == previous.timestamp for f in before) != 1
            or sum(f.timestamp == current.timestamp for f in after) != 1
        ):
            continue
        delta = Decimal(current.numeric_value) - Decimal(previous.numeric_value)
        if not delta:
            continue
        changes.append(
            Change(
                id="chg_" + digest([previous.evidence_id, current.evidence_id])[:16],
                name=current.name,
                previous_id=previous.evidence_id,
                current_id=current.evidence_id,
                previous_value=previous.value,
                current_value=current.value,
                delta=decimal_text(delta),
                unit=current.unit,
                direction="increased" if delta > 0 else "decreased",
            )
        )
    return sorted(changes, key=lambda change: change.name)


def make_claims(snapshot):
    facts = {fact.evidence_id: fact for fact in snapshot.facts}
    claims = []
    used = set()
    for change in snapshot.changes:
        previous, current = facts[change.previous_id], facts[change.current_id]
        text = (
            f"{current.name}: {previous.value} → {current.value} {change.unit} "
            f"({change.direction} by {decimal_text(abs(Decimal(change.delta)))} {change.unit}); "
            f"{previous.timestamp:%b %d %H:%M} → {current.timestamp:%b %d %H:%M} UTC."
        )
        claims.append(
            Claim(
                id=change.id, kind="change", text=text, evidence_ids=[change.previous_id, change.current_id]
            )
        )
        used.update([change.previous_id, change.current_id])
    latest = {}
    for fact in snapshot.facts:
        if (
            fact.timestamp
            and fact.date_precision == "instant"
            and fact.timestamp > snapshot.since
            and fact.evidence_id not in used
        ):
            group = (fact.kind, fact.code_system, fact.code or fact.name, fact.unit)
            if group not in latest or latest[group].timestamp < fact.timestamp:
                latest[group] = fact
    for fact in sorted(latest.values(), key=lambda item: item.timestamp, reverse=True):
        suffix = f" {fact.unit}" if fact.unit else ""
        text = f"{fact.name}: {fact.value}{suffix}, recorded {fact.timestamp:%b %d %H:%M} UTC."
        if fact.kind == "MedicationRequest":
            text = f"Medication order: {fact.name} ({fact.status}), authored {fact.timestamp:%b %d %H:%M} UTC. Administration is a separate record."
        if fact.kind == "MedicationAdministration":
            text = f"Administration record: {fact.name} ({fact.status}), {fact.timestamp:%b %d %H:%M} UTC."
        if fact.status == "corrected":
            text += " Source result is corrected."
        claims.append(
            Claim(
                id="clm_" + digest([fact.evidence_id])[:16],
                kind="recorded",
                text=text,
                evidence_ids=[fact.evidence_id],
            )
        )
    return claims


def verify_snapshot(snapshot):
    required = [item for item in snapshot.manifest if item.resource_type in REQUIRED_TYPES]
    if len(required) != len(REQUIRED_TYPES) or {item.resource_type for item in required} != set(
        REQUIRED_TYPES
    ):
        raise EvidenceIntegrityError("Missing required coverage manifest")
    expected_complete = all(
        item.state in {CoverageState.available, CoverageState.empty} and item.unknown_dates == 0
        for item in required
    )
    if snapshot.complete != expected_complete or (not snapshot.complete and snapshot.claims):
        raise EvidenceIntegrityError("Briefing completeness does not match retrieval coverage")
    request = RunRequest(
        patient_id=snapshot.patient_id,
        encounter_id=snapshot.encounter_id,
        window_start=snapshot.window_start,
        since=snapshot.since,
        as_of=snapshot.as_of,
    )
    normalized = {}
    for resource in snapshot.resources.values():
        if not check_subject(resource, request, snapshot.source_base) or resource.get("status") in {
            "entered-in-error",
            "cancelled",
            "draft",
        }:
            raise EvidenceIntegrityError("Evidence is outside the valid encounter context")
        timestamp, precision = event_time(resource)
        if timestamp and precision == "instant" and not request.window_start <= timestamp <= request.as_of:
            raise EvidenceIntegrityError("Evidence is outside the requested window")
        for fact in normalize_resource(resource, request):
            normalized[fact.evidence_id] = fact
    if normalized != {fact.evidence_id: fact for fact in snapshot.facts}:
        raise EvidenceIntegrityError("Normalized values do not match the raw evidence")
    ids = {fact.evidence_id for fact in snapshot.facts}
    if len(ids) != len(snapshot.facts):
        raise EvidenceIntegrityError("Duplicate evidence identifiers")
    for fact in snapshot.facts:
        resource = snapshot.resources.get(fact.resource_key)
        if not resource or digest(resource) != fact.resource_hash:
            raise EvidenceIntegrityError("Evidence hash mismatch")
    # Re-render every claim from normalized facts and deterministic changes.
    canonical_changes = calculate_changes(snapshot.facts, snapshot.since)
    if [c.model_dump() for c in canonical_changes] != [c.model_dump() for c in snapshot.changes]:
        raise EvidenceIntegrityError("Change calculations do not match evidence")
    canonical_claims = {claim.id: claim for claim in make_claims(snapshot)}
    if len({c.id for c in snapshot.claims}) != len(snapshot.claims):
        raise EvidenceIntegrityError("Duplicate claim identifiers")
    for claim in snapshot.claims:
        if not claim.evidence_ids or any(eid not in ids for eid in claim.evidence_ids):
            raise EvidenceIntegrityError("Unknown evidence reference")
        if claim.id not in canonical_claims or claim != canonical_claims[claim.id]:
            raise EvidenceIntegrityError("Claim does not match its evidence template")
    if snapshot.complete and set(canonical_claims) != {c.id for c in snapshot.claims}:
        raise EvidenceIntegrityError("Required evidence claims were omitted")
    return True


def build_snapshot(source: Source, request: RunRequest) -> Snapshot:
    started = perf_counter()
    patient = source.patient(request.patient_id)
    if patient.get("id") != request.patient_id:
        raise EvidenceIntegrityError("Patient read returned another patient")
    encounters = source.encounters(request.patient_id)
    encounter = next((e for e in encounters if e.get("id") == request.encounter_id), None)
    if not encounter or not matches_reference(
        encounter.get("subject", {}).get("reference", ""), "Patient", request.patient_id, source.base_url
    ):
        raise EvidenceIntegrityError("Encounter does not belong to the selected patient")
    snapshot = Snapshot(
        **request.model_dump(exclude={"scenario"}),
        source_base=source.base_url,
        manifest=[],
        facts=[],
        resources={},
    )
    for resource_type in REQUIRED_TYPES:
        try:
            resources = source.fetch(resource_type, request)
        except FHIRRequestError as exc:
            state = (
                CoverageState.access_denied if exc.status_code in {401, 403} else CoverageState.unavailable
            )
            snapshot.manifest.append(
                Coverage(
                    resource_type=resource_type,
                    state=state,
                    reason="Access denied"
                    if state == CoverageState.access_denied
                    else "Upstream retrieval failed",
                )
            )
            continue
        coverage = Coverage(
            resource_type=resource_type,
            state=CoverageState.available if resources else CoverageState.empty,
            count=len(resources),
        )
        seen = {}
        for resource in resources:
            if resource.get("resourceType") != resource_type or not resource.get("id"):
                raise EvidenceIntegrityError("Malformed resource in retrieval")
            if not check_subject(resource, request, source.base_url):
                coverage.excluded += 1
                continue
            # Search should return the current version once. Conflicting versions fail closed.
            identity = f"{resource_type}/{resource['id']}"
            if identity in seen:
                if seen[identity] != digest(resource):
                    raise EvidenceIntegrityError("Conflicting resource versions in search")
                continue
            seen[identity] = digest(resource)
            if resource.get("status") in {"entered-in-error", "cancelled", "draft"}:
                coverage.excluded += 1
                continue
            timestamp, precision = event_time(resource)
            if (
                timestamp
                and precision == "instant"
                and (timestamp < request.window_start or timestamp > request.as_of)
            ):
                coverage.excluded += 1
                continue
            if not timestamp or precision != "instant":
                coverage.unknown_dates += 1
            key, _, _ = resource_identity(resource)
            snapshot.resources[key] = resource
            facts = normalize_resource(resource, request)
            coverage.stale_count += sum(f.stale for f in facts)
            snapshot.facts.extend(facts)
        snapshot.manifest.append(coverage)
    snapshot.manifest.extend(
        Coverage(resource_type=rt, state=CoverageState.not_queried, reason="Outside this briefing's scope")
        for rt in NOT_QUERIED
    )
    snapshot.facts.sort(
        key=lambda fact: (fact.timestamp.isoformat() if fact.timestamp else "", fact.evidence_id),
        reverse=True,
    )
    snapshot.complete = all(
        c.state in {CoverageState.available, CoverageState.empty} and c.unknown_dates == 0
        for c in snapshot.manifest
        if c.resource_type in REQUIRED_TYPES
    )
    if not snapshot.complete:
        snapshot.warnings.append(
            "Briefing withheld: required retrieval or event-time coverage is incomplete. Inspect the retrieval manifest."
        )
    if any(f.stale for f in snapshot.facts):
        snapshot.warnings.append(
            "Some records are older than 12 hours at the replay time. They remain visible as historical evidence."
        )
    if any(f.status == "corrected" for f in snapshot.facts):
        snapshot.warnings.append(
            "Corrected results are present. Only the retrieved current resource version is used."
        )
    snapshot.changes = calculate_changes(snapshot.facts, snapshot.since)
    if snapshot.complete:
        snapshot.claims = make_claims(snapshot)
    if not snapshot.claims and snapshot.complete:
        snapshot.warnings.append(
            "No supported changes or records after the review boundary; no briefing was generated."
        )
    verify_snapshot(snapshot)
    snapshot.telemetry = {
        "retrieval_ms": round((perf_counter() - started) * 1000, 2),
        "input_tokens": 0,
        "output_tokens": 0,
        "model_calls": 0,
        "estimated_cost_usd": 0.0,
    }
    # Stable evidence fingerprint excludes wall-clock telemetry and generation order.
    snapshot.snapshot_hash = digest(
        snapshot.model_dump(mode="json", exclude={"snapshot_hash", "telemetry", "engine"})
    )
    return snapshot

from copy import deepcopy
from datetime import timedelta

import pytest

from workbench.demo import DEMO_CLOCK
from workbench.domain import RunRequest
from workbench.pipeline import EvidenceIntegrityError, build_snapshot, verify_snapshot
from workbench.sources import DemoSource
from workbench.sources import FHIRSource
from unittest.mock import Mock


@pytest.fixture
def v2_request():
    return RunRequest(
        patient_id="demo-avery",
        encounter_id="enc-avery",
        window_start=DEMO_CLOCK - timedelta(hours=36),
        since=DEMO_CLOCK - timedelta(hours=14),
        as_of=DEMO_CLOCK,
    )


def test_snapshots_have_reproducible_hashes_and_exact_decimal_changes(v2_request):
    first, second = build_snapshot(DemoSource(), v2_request), build_snapshot(DemoSource(), v2_request)
    assert first.snapshot_hash == second.snapshot_hash
    assert {c.name: c.delta for c in first.changes} == {"Creatinine": "0.6", "Hemoglobin": "-0.3"}
    assert verify_snapshot(first)
    assert all("error-result" not in fact.resource_key for fact in first.facts)
    assert any(f.status == "corrected" and f.version == "2" for f in first.facts)


@pytest.mark.parametrize("scenario,state", [("outage", "unavailable"), ("denied", "access_denied")])
def test_retrieval_missingness_withholds_claims(v2_request, scenario, state):
    snapshot = build_snapshot(DemoSource(), v2_request.model_copy(update={"scenario": scenario}))
    assert not snapshot.complete
    assert not snapshot.claims
    assert any(c.state == state for c in snapshot.manifest)


def test_unknown_dates_are_visible_but_never_treated_as_recent(v2_request):
    snapshot = build_snapshot(
        DemoSource(), v2_request.model_copy(update={"patient_id": "demo-riley", "encounter_id": "enc-riley"})
    )
    assert not snapshot.complete
    assert any(f.timestamp is None and f.date_precision == "unknown" for f in snapshot.facts)
    assert not snapshot.claims


def test_foreign_patient_in_search_fails_isolation(v2_request):
    class Foreign(DemoSource):
        def fetch(self, resource_type, request):
            rows = super().fetch(resource_type, request)
            if rows:
                rows[0]["subject"]["reference"] = "Patient/demo-jordan"
            return rows

    with pytest.raises(EvidenceIntegrityError, match="isolation"):
        build_snapshot(Foreign(), v2_request)


@pytest.mark.parametrize("reference", ["Group/demo-avery", "https://foreign.example/fhir/Patient/demo-avery"])
def test_patient_ids_cannot_be_matched_across_resource_types_or_issuers(v2_request, reference):
    class ForeignReference(DemoSource):
        def fetch(self, resource_type, request):
            rows = super().fetch(resource_type, request)
            if rows:
                rows[0]["subject"]["reference"] = reference
            return rows

    with pytest.raises(EvidenceIntegrityError, match="isolation"):
        build_snapshot(ForeignReference(), v2_request)


def test_wrong_encounter_and_future_data_cannot_enter_snapshot(v2_request):
    class Altered(DemoSource):
        def fetch(self, resource_type, request):
            rows = super().fetch(resource_type, request)
            if resource_type == "Observation":
                extra = deepcopy(rows[0])
                extra["id"] = "other-encounter"
                extra["encounter"]["reference"] = "Encounter/another"
                future = deepcopy(rows[0])
                future["id"] = "future"
                future["effectiveDateTime"] = "2026-10-23T10:00:00Z"
                rows.extend([extra, future])
            return rows

    snapshot = build_snapshot(Altered(), v2_request)
    assert all(
        "other-encounter" not in f.resource_key and "future" not in f.resource_key for f in snapshot.facts
    )


def test_mixed_units_and_comparators_never_create_false_deltas(v2_request):
    class ChangedUnits(DemoSource):
        def fetch(self, resource_type, request):
            rows = super().fetch(resource_type, request)
            for row in rows:
                if row["id"] == "creat-current":
                    row["valueQuantity"].update(value=159, unit="umol/L", code="umol/L")
                if row["id"] == "hgb-current":
                    row["valueQuantity"]["comparator"] = "<"
            return rows

    snapshot = build_snapshot(ChangedUnits(), v2_request)
    assert not snapshot.changes
    assert any(f.value == "< 11.8" for f in snapshot.facts)


@pytest.mark.parametrize("tamper", ["numeric", "citation", "claim", "raw", "omission", "time"])
def test_verifier_rejects_unsupported_changes(v2_request, tamper):
    snapshot = build_snapshot(DemoSource(), v2_request)
    if tamper == "numeric":
        snapshot.facts[0].numeric_value = "999"
    elif tamper == "citation":
        snapshot.claims[0].evidence_ids = ["invented"]
    elif tamper == "claim":
        snapshot.claims[0].text = "Invented diagnosis and quantity 999"
    elif tamper == "raw":
        next(iter(snapshot.resources.values()))["status"] = "entered-in-error"
    elif tamper == "time":
        snapshot.facts[0].timestamp = DEMO_CLOCK + timedelta(hours=1)
    else:
        snapshot.claims.pop()
    with pytest.raises(EvidenceIntegrityError):
        verify_snapshot(snapshot)


def test_partial_dates_cannot_establish_a_review_boundary(v2_request):
    class DateOnly(DemoSource):
        def fetch(self, resource_type, request):
            rows = super().fetch(resource_type, request)
            if rows and resource_type == "Observation":
                rows[0]["effectiveDateTime"] = "2026-10-22"
            return rows

    snapshot = build_snapshot(DateOnly(), v2_request)
    assert not snapshot.complete
    assert any(f.date_precision == "day" for f in snapshot.facts)


def test_conflicting_versions_fail_instead_of_double_counting(v2_request):
    class Conflicting(DemoSource):
        def fetch(self, resource_type, request):
            rows = super().fetch(resource_type, request)
            if resource_type == "Observation":
                conflict = deepcopy(rows[0])
                conflict["meta"]["versionId"] = "999"
                rows.append(conflict)
            return rows

    with pytest.raises(EvidenceIntegrityError, match="Conflicting"):
        build_snapshot(Conflicting(), v2_request)


def test_medication_administrations_use_r4_context(v2_request):
    source = FHIRSource("http://localhost:8080/fhir", "test-token")
    source.client._search = Mock(return_value=[])
    source.fetch("MedicationAdministration", v2_request)
    params = source.client._search.call_args.args[1]
    assert params["context"] == "Encounter/enc-avery" and "encounter" not in params
    assert "effective-time" in params

    class Administration(DemoSource):
        def fetch(self, resource_type, request):
            if resource_type == "MedicationAdministration":
                return [
                    {
                        "resourceType": resource_type,
                        "id": "admin-1",
                        "status": "completed",
                        "subject": {"reference": "Patient/demo-avery"},
                        "context": {"reference": "Encounter/enc-avery"},
                        "effectiveDateTime": "2026-10-22T11:00:00Z",
                        "medicationCodeableConcept": {"text": "Synthetic administered medication"},
                    }
                ]
            return super().fetch(resource_type, request)

    result = build_snapshot(Administration(), v2_request)
    assert any(f.kind == "MedicationAdministration" for f in result.facts)
    assert any("Administration record:" in claim.text for claim in result.claims)


def test_periods_are_not_misrepresented_as_instant_measurements(v2_request):
    class Period(DemoSource):
        def fetch(self, resource_type, request):
            rows = super().fetch(resource_type, request)
            if resource_type == "Observation":
                rows[0].pop("effectiveDateTime")
                rows[0]["effectivePeriod"] = {"start": "2026-10-20T18:00:00Z", "end": "2026-10-22T12:00:00Z"}
            return rows

    result = build_snapshot(Period(), v2_request)
    assert not result.complete and not result.claims
    assert any(fact.date_precision == "period" for fact in result.facts)

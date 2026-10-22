from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from ingestion.converter import entry_to_facts, parse_fhir_date
from ingestion.engine import FactTableBuilder


@pytest.mark.parametrize("value", ["2025", "2025-02", "2025-02-14", "2025-02-14T09:00:00Z", None, "invalid"])
def test_all_parsed_dates_can_be_sorted_together(value):
    parsed = parse_fhir_date(value)
    assert parsed.tzinfo == timezone.utc
    sorted([parsed, datetime.now(timezone.utc)])


def test_dates_preserve_instant_and_support_partial_precision():
    assert parse_fhir_date("2025-02-14T01:00:00-08:00") == parse_fhir_date("2025-02-14T09:00:00Z")
    assert parse_fhir_date("2025-02") == datetime(2025, 2, 1, tzinfo=timezone.utc)


def test_blood_pressure_components_keep_values_and_source():
    resource = {
        "resourceType": "Observation", "id": "bp", "status": "final",
        "subject": {"reference": "Patient/p"},
        "category": [{"coding": [{"code": "vital-signs"}]}],
        "effectiveDateTime": "2025-02-14T09:00:00Z",
        "component": [
            {"code": {"text": "Systolic pressure"}, "valueQuantity": {"value": 120, "code": "mm[Hg]"}},
            {"code": {"text": "Diastolic pressure"}, "valueQuantity": {"value": 80, "code": "mm[Hg]"}},
        ],
    }
    facts = entry_to_facts({"resource": resource})
    assert [(fact.name, fact.value, fact.unit) for fact in facts] == [
        ("Systolic pressure", "120", "mm[Hg]"), ("Diastolic pressure", "80", "mm[Hg]")
    ]
    assert all(fact.source_id == "Observation/bp" for fact in facts)


def test_fact_builder_handles_missing_dates_and_does_not_invent_administration_counts():
    client = Mock()
    client.search_encounters.return_value = [{"resourceType": "Encounter", "id": "e"}]
    client.search_observations.side_effect = [[{
        "resourceType": "Observation", "id": "o", "effectiveDateTime": "2025-02-14T09:00:00Z",
    }], []]
    client.search_medication_requests.return_value = [{
        "resourceType": "MedicationRequest", "id": "m", "authoredOn": "2025-02-14",
    }]
    facts = FactTableBuilder(client).build_fact_table("p")
    warning = facts[0]
    assert "not retrieved" in warning.value
    assert "0 administrations" not in warning.value
    assert [fact.source_id for fact in facts[1:]] == ["Observation/o", "MedicationRequest/m", "Encounter/e"]

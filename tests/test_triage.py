from datetime import datetime, timezone

import pytest

from ingestion.models import Fact, FactType
from ui.triage import _classify_fact


@pytest.mark.parametrize("name,value,unit", [
    ("Glucose", "5.5", "mmol/L"), ("Creatinine", "90", "umol/L"),
    ("Hemoglobin", "135", "unknown"), ("Sodium", "140", None),
])
def test_unknown_units_are_not_compared_to_incompatible_thresholds(name, value, unit):
    fact = Fact("p", datetime.now(timezone.utc), FactType.LAB, name, value, unit)
    assert _classify_fact(fact)[0] == "info"


def test_data_quality_warnings_are_separate_from_critical_measurements():
    fact = Fact("p", datetime.now(timezone.utc), FactType.OTHER, "Data Quality Warning", "Not retrieved")
    assert _classify_fact(fact)[0] == "info"


def test_supported_unit_still_uses_existing_demo_rule():
    fact = Fact("p", datetime.now(timezone.utc), FactType.LAB, "Glucose", "350", "mg/dL")
    assert _classify_fact(fact)[0] == "critical"

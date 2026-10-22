from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

import main
from fhir.client import FHIRClient, FHIRRequestError
from ingestion.models import Fact, FactType


APP = str(Path(__file__).resolve().parents[1] / "src" / "ui" / "app.py")


def test_changing_patient_clears_previous_summary(monkeypatch, db_session_factory):
    monkeypatch.setattr(FHIRClient, "_get", Mock(return_value={
        "resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1", "name": [{"given": ["One"]}]}},
            {"resource": {"resourceType": "Patient", "id": "p2", "name": [{"given": ["Two"]}]}},
        ],
    }))
    fact = Fact("p1", datetime(2025, 2, 14, tzinfo=timezone.utc), FactType.LAB,
                "Hemoglobin", "13.5", "g/dL", source_id="Observation/o")
    monkeypatch.setattr(main, "run_pipeline", Mock(return_value={
        "patient_id": "p1", "patient_name": "One", "facts_raw": [fact],
        "facts_markdown": "original date 2025-02-14", "llm_facts_markdown": "redacted [DATE]",
        "summary": "Patient one summary", "audit_id": None,
    }))
    app = AppTest.from_file(APP, default_timeout=15).run()
    assert not app.exception
    next(button for button in app.button if button.label == "Generate Summary").click().run()
    assert not app.exception
    assert any("Patient one summary" in item.value for item in app.markdown)
    assert app.code[0].value == "redacted [DATE]"
    next(select for select in app.selectbox if select.label == "Patient ID").select("p2").run()
    assert not app.exception
    assert app.session_state["results"] is None
    assert not any("Patient one summary" in item.value for item in app.markdown)


def test_unavailable_fhir_shows_error_instead_of_crashing(monkeypatch, db_session_factory):
    monkeypatch.setattr(FHIRClient, "_get", Mock(side_effect=FHIRRequestError("FHIR unavailable")))
    app = AppTest.from_file(APP, default_timeout=15).run()
    next(button for button in app.button if button.label == "Refresh Patients").click().run()
    assert not app.exception
    assert any("FHIR unavailable" in item.value for item in app.error)

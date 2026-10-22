from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

import main
from db.models import AuditLog
from fhir.client import FHIRRequestError
from ingestion.models import Fact, FactType
from llm.client import LLMGenerationError


@pytest.fixture
def pipeline(monkeypatch, db_session_factory):
    fhir = Mock()
    fhir.get_patient.return_value = {"resourceType": "Patient", "id": "p", "name": []}
    monkeypatch.setattr(main, "FHIRClient", Mock(return_value=fhir))
    facts = [Fact("p", datetime(2025, 2, 14, tzinfo=timezone.utc), FactType.LAB,
                  "Hemoglobin", "13.5", "g/dL", source_id="Observation/o")]
    builder = Mock()
    builder.build_fact_table.return_value = facts
    monkeypatch.setattr(main, "FactTableBuilder", Mock(return_value=builder))
    llm = Mock(model="test-model")
    llm.generate_summary.return_value = "Hemoglobin 13.5 g/dL [[Observation/o]]."
    monkeypatch.setattr(main, "LLMClient", Mock(return_value=llm))
    monkeypatch.setattr(main, "SessionLocal", db_session_factory)
    return fhir, builder, llm


def test_pipeline_redacts_input_and_saves_audit(pipeline, db_session_factory):
    _, _, llm = pipeline
    result = main.run_pipeline("p", api_key="test-key")
    assert result["patient_name"] == "Unknown"
    assert result["patient_id"] == "p"
    assert result["audit_id"]
    assert "2025-02-14" not in result["llm_facts_markdown"]
    assert "[[Observation/o]]" in result["llm_facts_markdown"]
    assert result["llm_facts_markdown"] in llm.generate_summary.call_args.args[1]
    with db_session_factory() as db:
        assert db.query(AuditLog).one().summary_text == result["summary"]


@pytest.mark.parametrize("stage", ["patient", "facts", "model", "empty"])
def test_pipeline_failures_never_save_a_successful_summary(pipeline, db_session_factory, stage):
    fhir, builder, llm = pipeline
    if stage == "patient":
        fhir.get_patient.side_effect = FHIRRequestError("FHIR unavailable")
    elif stage == "facts":
        builder.build_fact_table.side_effect = FHIRRequestError("Incomplete retrieval")
    elif stage == "model":
        llm.generate_summary.side_effect = LLMGenerationError("Model unavailable")
    else:
        builder.build_fact_table.return_value = []
    result = main.run_pipeline("p", api_key="test-key")
    assert "error" in result
    assert "summary" not in result
    with db_session_factory() as db:
        assert db.query(AuditLog).count() == 0


def test_audit_failure_is_explicit(pipeline, monkeypatch):
    db = Mock()
    db.commit.side_effect = RuntimeError("database unavailable")
    monkeypatch.setattr(main, "SessionLocal", Mock(return_value=db))
    result = main.run_pipeline("p", api_key="test-key")
    assert result["summary"]
    assert result["audit_id"] is None
    assert "Audit logging failed" in result["audit_warning"]
    db.rollback.assert_called_once()
    db.close.assert_called_once()

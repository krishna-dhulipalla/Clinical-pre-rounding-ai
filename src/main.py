import logging
import os
import json
from datetime import datetime
from fhir.client import FHIRClient, FHIRRequestError
from ingestion.engine import FactTableBuilder
from llm.client import LLMClient, LLMGenerationError
from llm.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from db.database import SessionLocal, init_db
from db.models import AuditLog
from redaction.engine import Redactor

# Config Init
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_fhir_base_url() -> str:
    """Returns configured FHIR base URL with a safe local default."""
    return os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir")

def run_pipeline(patient_id: str, api_key: str = None):
    """
    Runs the full summarization pipeline for a given patient_id.
    Returns a dictionary with facts, summary, and audit_id.
    """
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
        
    client = FHIRClient(base_url=get_fhir_base_url())
    
    # 1. Fetch Patient Details
    try:
        patient = client.get_patient(patient_id)
    except FHIRRequestError as exc:
        return {"error": str(exc)}
    if not patient:
        return {"error": f"Patient {patient_id} not found"}
        
    name = "Unknown"
    if patient.get("name"):
        family = patient["name"][0].get("family", "")
        given = " ".join(patient["name"][0].get("given", []))
        name = f"{given} {family}".strip() or "Unknown"
            
    logger.info("Generating patient summary")

    # 2. Build Fact Table
    builder = FactTableBuilder(client)
    try:
        facts = builder.build_fact_table(patient_id)
    except FHIRRequestError as exc:
        return {"error": str(exc)}
    if not facts:
        return {"error": "No supported clinical facts were found. A summary was not generated."}
    
    # Convert to Markdown
    facts_markdown = "\n".join([f.to_markdown() for f in facts])
    
    # --- REDACTION LAYER ---
    redactor = Redactor(patient_name=name)
    redacted_markdown = redactor.redact(facts_markdown)
    # -----------------------

    # Serialized facts for Audit Log
    facts_json = [
        {
            "timestamp": f.timestamp.isoformat(),
            "type": f.type.value,
            "name": f.name,
            "value": f.value,
            "unit": f.unit,
            "source_id": f.source_id
        }
        for f in facts
    ]

    # 3. Generate Summary
    try:
        llm = LLMClient(api_key=api_key)
        user_prompt = USER_PROMPT_TEMPLATE.format(facts_markdown=redacted_markdown)
        summary = llm.generate_summary(SYSTEM_PROMPT, user_prompt)
    except LLMGenerationError as exc:
        return {"error": str(exc)}

    # 4. Audit Log
    db = SessionLocal()
    audit_warning = None
    try:
        audit_entry = AuditLog(
            patient_id=patient_id,
            facts_json=facts_json,
            summary_text=summary,
            llm_model=llm.model,
            timestamp=datetime.utcnow()
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)
        audit_id = audit_entry.id
    except Exception as e:
        db.rollback()
        logger.error("Failed to write audit log (%s)", type(e).__name__)
        audit_id = None
        audit_warning = "Audit logging failed for this summary. Feedback cannot be saved."
    finally:
        db.close()

    return {
        "patient_name": name,
        "patient_id": patient_id,
        "facts_markdown": facts_markdown,
        "llm_facts_markdown": redacted_markdown,
        "facts_raw": facts,
        "summary": summary,
        "audit_id": str(audit_id) if audit_id else None,
        "audit_warning": audit_warning,
    }

def main():
    # Setup LLM - Check for API Key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY is not set. LLM generation may fail.")

    # Find a valid patient
    client = FHIRClient(base_url=get_fhir_base_url())
    patients_bundle = client._get("Patient", params={"_count": 1})
    entries = patients_bundle.get("entry", [])
    if not entries:
        print("No patients found in FHIR server. Please run 'python scripts/load_synthea.py' first.")
        return

    patient_id = entries[0]["resource"]["id"]
    print(f"Found Patient ID: {patient_id}. Running pipeline...")

    # Run pipeline
    result = run_pipeline(patient_id, api_key=api_key)
    
    if "error" in result:
        print(result["error"])
    else:
        print(f"Summary for {result['patient_name']}:\n")
        print(result["summary"])

if __name__ == "__main__":
    # Ensure tables exist (quick check)
    # init_db() 
    main()

import sys
import os
sys.path.append(os.path.abspath("src"))

from db.database import SessionLocal, init_db
from db.models import AuditLog
import uuid
from datetime import datetime

def test_audit_log_creation(db_session_factory):
    # Ensure tables exist
    init_db()
    
    db = db_session_factory()
    try:
        log_id = uuid.uuid4()
        entry = AuditLog(
            id=log_id,
            patient_id="test-patient",
            facts_json=[{"test": "fact"}],
            summary_text="Is a summary",
            llm_model="test-model",
            timestamp=datetime.utcnow()
        )
        db.add(entry)
        db.commit()
        
        # Verify
        saved = db.query(AuditLog).filter(AuditLog.id == log_id).first()
        assert saved is not None
        assert saved.patient_id == "test-patient"
        print("Audit Log Test Passed!")
    finally:
        db.close()

from sqlalchemy import Column, String, DateTime, Text, Integer, JSON, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import uuid
from .database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, default=datetime.utcnow)
    patient_id = Column(String, index=True)
    facts_json = Column(JSON().with_variant(JSONB, "postgresql"))
    summary_text = Column(Text)
    llm_model = Column(String)
    feedback_score = Column(Integer, nullable=True) # 0 or 1 for incorrect/correct
    feedback_text = Column(Text, nullable=True)

from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import AuditLog
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

def submit_feedback(audit_id: str, score: int, text: str = None) -> bool:
    """
    Updates the Audit Log entry with feedback.
    score: 1 (Positive/Correct), 0 (Negative/Incorrect)
    """
    try:
        log_id = UUID(str(audit_id))
    except (ValueError, TypeError, AttributeError):
        return False
    if score not in (0, 1):
        return False

    db = SessionLocal()
    try:
        log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
        if not log:
            logger.warning(f"Audit Log {audit_id} not found for feedback.")
            return False
        
        log.feedback_score = score
        log.feedback_text = text
        db.commit()
        return True
    except Exception as e:
        logger.error("Failed to submit feedback (%s)", type(e).__name__)
        db.rollback()
        return False
    finally:
        db.close()

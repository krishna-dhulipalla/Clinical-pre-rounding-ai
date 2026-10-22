import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from db.database import SessionLocal
from db.models import AuditLog
from eval.judge import LLMJudge
from sqlalchemy import desc
from redaction.engine import Redactor

def run_evaluation(limit: int = 5):
    db = SessionLocal()
    try:
        # Fetch recent logs that haven't been evaluated? 
        # For now, just fetch the last N logs.
        logs = db.query(AuditLog).order_by(desc(AuditLog.timestamp)).limit(limit).all()
        
        if not logs:
            print("No audit logs found to evaluate.")
            return

        judge = LLMJudge()
        print(f"Starting Evaluation for {len(logs)} recent logs...\n")
        
        total_score = 0
        
        for log in logs:
            print(f"--- Evaluating Log ID: {log.id} ---")
            # Reconstruct facts text from JSON
            redactor = Redactor()
            facts_text = redactor.redact(json.dumps(log.facts_json, indent=2))
            
            result = judge.evaluate(facts_text, redactor.redact(log.summary_text))
            
            score = result.get("score", 0)
            total_score += score
            
            print(f"Score: {score}/10")
            print(f"Reasoning: {result.get('reasoning')}")
            if result.get("hallucinations"):
                print(f"Hallucinations: {result.get('hallucinations')}")
            print("\n")

        avg_score = total_score / len(logs)
        print("-------------------------------")
        print(f"Average Quality Score: {avg_score:.2f}/10")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_evaluation()

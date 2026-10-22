import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        try:
            payload = json.loads(record.getMessage())
        except (ValueError, TypeError):
            payload = {"event": record.getMessage()}
        payload.update({"level": record.levelname, "timestamp": datetime.now(timezone.utc).isoformat()})
        for key in ("trace_id", "job_status", "duration_ms", "failure_type", "worker_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)


def configure_logging():
    logger = logging.getLogger("workbench")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

"""Explicit retention job; previews counts unless --apply is supplied."""

import argparse
import json
from time import time

from sqlalchemy import delete, select

from .persistence import AccessEvent, OAuthFlow, ReviewRow, RunRow, SessionRow, SnapshotRow


def purge(database, retention_days=90, audit_days=365, apply=False):
    if retention_days < 1 or audit_days < retention_days:
        raise ValueError("Retain runs for at least one day and audits at least as long as runs")
    now = time()
    with database.sessions.begin() as db:
        ids = list(
            db.scalars(
                select(RunRow.id).where(
                    RunRow.created_at < now - retention_days * 86400,
                    RunRow.status.in_(["completed", "abstained", "failed", "cancelled"]),
                )
            )
        )
        sessions = list(db.scalars(select(SessionRow.token_hash).where(SessionRow.expires_at < now)))
        audits = list(
            db.scalars(select(AccessEvent.id).where(AccessEvent.created_at < now - audit_days * 86400))
        )
        counts = {
            "runs": len(ids),
            "expired_sessions": len(sessions),
            "audit_events": len(audits),
            "applied": apply,
        }
        if apply:
            db.execute(delete(ReviewRow).where(ReviewRow.run_id.in_(ids)))
            db.execute(delete(SnapshotRow).where(SnapshotRow.run_id.in_(ids)))
            db.execute(delete(RunRow).where(RunRow.id.in_(ids)))
            db.execute(delete(SessionRow).where(SessionRow.token_hash.in_(sessions)))
            db.execute(delete(OAuthFlow).where(OAuthFlow.expires_at < now))
            db.execute(delete(AccessEvent).where(AccessEvent.id.in_(audits)))
        return counts


def main():
    from .config import Settings
    from .persistence import Database

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retention-days", type=int, default=90)
    parser.add_argument("--audit-days", type=int, default=365)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            purge(
                Database(Settings.from_env().database_url), args.retention_days, args.audit_days, args.apply
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

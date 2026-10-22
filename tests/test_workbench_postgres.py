"""Runs in CI against a disposable PostgreSQL database, never the app database."""

from datetime import timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url

from workbench.config import Settings
from workbench.demo import DEMO_CLOCK
from workbench.domain import ReviewRequest, RunRequest
from workbench.persistence import Database
from workbench.security import Auth
from workbench.service import Workbench
from workbench.worker import Worker


@pytest.mark.skipif(
    not os.getenv("WORKBENCH_TEST_POSTGRES_URL"), reason="Disposable PostgreSQL URL not configured"
)
def test_postgres_migrations_jobs_snapshots_and_review():
    url = os.environ["WORKBENCH_TEST_POSTGRES_URL"]
    assert make_url(url).database.endswith("_test"), "Use a disposable database ending in _test"
    database = Database(url)
    database.migrate()
    assert database.ready()
    settings = Settings(database_url=url, embedded_worker=False)
    auth = Auth(database, settings)
    _, user = auth.demo_session()
    service = Workbench(database, settings, auth)
    request = RunRequest(
        patient_id="demo-avery",
        encounter_id="enc-avery",
        window_start=DEMO_CLOCK - timedelta(hours=36),
        since=DEMO_CLOCK - timedelta(hours=14),
        as_of=DEMO_CLOCK,
    )
    job = service.enqueue(user, request, str(uuid4()), str(uuid4()))
    Worker(database, settings, auth).run_once()
    result = service.detail(user, job["id"], str(uuid4()))
    assert result["status"] == "completed"
    review = ReviewRequest(
        expected_revision=0,
        selected_claim_ids=[claim["id"] for claim in result["snapshot"]["claims"]],
        accept=True,
    )
    assert service.review(user, job["id"], review, str(uuid4()))["review_status"] == "accepted"
    database.engine.dispose()

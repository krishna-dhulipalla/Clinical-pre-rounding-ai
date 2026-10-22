from pathlib import Path
from time import time
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    Float,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    ForeignKey,
    create_engine,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import ROOT

Base = declarative_base()
JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class RunRow(Base):
    __tablename__ = "wb_runs"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id = Column(String(128), nullable=False, index=True)
    session_hash = Column(String(64), nullable=True)
    patient_id = Column(String(64), nullable=False, index=True)
    encounter_id = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    request_json = Column(JSON_VALUE, nullable=False)
    status = Column(String(24), nullable=False, default="queued", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String(36), nullable=True)
    lease_until = Column(Float, nullable=True)
    created_at = Column(Float, nullable=False, default=time)
    updated_at = Column(Float, nullable=False, default=time)
    error_code = Column(String(64), nullable=True)
    revision = Column(Integer, nullable=False, default=0)
    review_status = Column(String(24), nullable=False, default="draft")
    trace_id = Column(String(36), nullable=False)


class SnapshotRow(Base):
    __tablename__ = "wb_snapshots"
    run_id = Column(String(36), ForeignKey("wb_runs.id"), primary_key=True)
    payload = Column(JSON_VALUE, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    created_at = Column(Float, nullable=False, default=time)


class ReviewRow(Base):
    __tablename__ = "wb_reviews"
    __table_args__ = (UniqueConstraint("run_id", "revision"),)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id = Column(String(36), ForeignKey("wb_runs.id"), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    actor_id = Column(String(128), nullable=False)
    selected_claim_ids = Column(JSON_VALUE, nullable=False)
    note = Column(Text, nullable=False, default="")
    status = Column(String(24), nullable=False)
    snapshot_hash = Column(String(64), nullable=False)
    created_at = Column(Float, nullable=False, default=time)


class AccessEvent(Base):
    __tablename__ = "wb_access_events"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id = Column(String(128), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    patient_id = Column(String(64), nullable=True)
    run_id = Column(String(36), nullable=True)
    trace_id = Column(String(36), nullable=False)
    outcome = Column(String(16), nullable=False, default="allowed")
    created_at = Column(Float, nullable=False, default=time)


class SessionRow(Base):
    __tablename__ = "wb_sessions"
    token_hash = Column(String(64), primary_key=True)
    actor_id = Column(String(128), nullable=False)
    display_name = Column(String(128), nullable=False)
    patient_ids = Column(JSON_VALUE, nullable=False)
    encounter_id = Column(String(64), nullable=True)
    token_ciphertext = Column(Text, nullable=True)
    fhir_url = Column(Text, nullable=True)
    expires_at = Column(Float, nullable=False)
    created_at = Column(Float, nullable=False, default=time)


class OAuthFlow(Base):
    __tablename__ = "wb_oauth_flows"
    state_hash = Column(String(64), primary_key=True)
    browser_hash = Column(String(64), nullable=False)
    verifier = Column(String(128), nullable=False)
    token_url = Column(Text, nullable=False)
    fhir_url = Column(Text, nullable=False)
    expires_at = Column(Float, nullable=False)


def immutable(mapper, connection, target):
    raise ValueError("Snapshots and review revisions are append-only")


for model in (SnapshotRow, ReviewRow, AccessEvent):
    event.listen(model, "before_update", immutable)


class Database:
    def __init__(self, url):
        if url.startswith("sqlite:///"):
            target = url.removeprefix("sqlite:///")
            if target != ":memory:":
                Path(target).parent.mkdir(parents=True, exist_ok=True)
        kwargs = (
            {"connect_args": {"check_same_thread": False, "timeout": 15}}
            if url.startswith("sqlite")
            else {"pool_pre_ping": True}
        )
        self.engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def configure_sqlite(connection, record):
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA foreign_keys=ON")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self):
        config = Config()
        config.set_main_option("script_location", str(ROOT / "migrations"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def ready(self):
        from sqlalchemy import text

        with self.engine.connect() as connection:
            return (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "0001_workbench"
            )

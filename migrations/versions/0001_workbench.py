"""Initial v2 schema, separate from legacy audit_logs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_workbench"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    json_type = sa.JSON().with_variant(JSONB, "postgresql")
    op.create_table(
        "wb_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("session_hash", sa.String(64)),
        sa.Column("patient_id", sa.String(64), nullable=False),
        sa.Column("encounter_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request_json", json_type, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("lease_owner", sa.String(36)),
        sa.Column("lease_until", sa.Float),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key"),
    )
    for column in ("owner_id", "patient_id", "status"):
        op.create_index(f"ix_wb_runs_{column}", "wb_runs", [column])
    op.create_table(
        "wb_snapshots",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("wb_runs.id"), primary_key=True),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_table(
        "wb_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("wb_runs.id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("selected_claim_ids", json_type, nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.UniqueConstraint("run_id", "revision"),
    )
    op.create_index("ix_wb_reviews_run_id", "wb_reviews", ["run_id"])
    op.create_table(
        "wb_access_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("patient_id", sa.String(64)),
        sa.Column("run_id", sa.String(36)),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_wb_access_events_actor_id", "wb_access_events", ["actor_id"])
    op.create_table(
        "wb_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("patient_ids", json_type, nullable=False),
        sa.Column("encounter_id", sa.String(64)),
        sa.Column("token_ciphertext", sa.Text),
        sa.Column("fhir_url", sa.Text),
        sa.Column("expires_at", sa.Float, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_table(
        "wb_oauth_flows",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("verifier", sa.String(128), nullable=False),
        sa.Column("token_url", sa.Text, nullable=False),
        sa.Column("fhir_url", sa.Text, nullable=False),
        sa.Column("expires_at", sa.Float, nullable=False),
    )


def downgrade():
    for table in (
        "wb_oauth_flows",
        "wb_sessions",
        "wb_access_events",
        "wb_reviews",
        "wb_snapshots",
        "wb_runs",
    ):
        op.drop_table(table)

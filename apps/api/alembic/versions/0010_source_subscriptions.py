"""add scheduled source subscriptions and scan history

Revision ID: 0010_source_subscriptions
Revises: 0009_source_document_store
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_source_subscriptions"
down_revision = "0009_source_document_store"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"


def _enable_rls(table_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY "{POLICY_NAME}" ON "{table_name}"
            USING (
                organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
            )
            WITH CHECK (
                organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
            )'''
    )


def upgrade() -> None:
    op.create_table(
        "source_subscriptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("connector", sa.String(length=32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("pause_reason", sa.String(length=80), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("next_scan_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("etag", sa.String(length=500), nullable=True),
        sa.Column("last_modified", sa.String(length=500), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("total_scans", sa.Integer(), nullable=False),
        sa.Column("total_changes", sa.Integer(), nullable=False),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outcome", sa.String(length=40), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "connector",
            "url_hash",
            name="uq_source_subscription_org_connector_url",
        ),
    )
    op.create_index("ix_source_subscriptions_organization_id", "source_subscriptions", ["organization_id"])
    op.create_index("ix_source_subscriptions_connector", "source_subscriptions", ["connector"])
    op.create_index("ix_source_subscriptions_url_hash", "source_subscriptions", ["url_hash"])
    op.create_index("ix_source_subscriptions_status", "source_subscriptions", ["status"])
    op.create_index("ix_source_subscriptions_next_scan_at", "source_subscriptions", ["next_scan_at"])
    op.create_index("ix_source_subscriptions_lease_until", "source_subscriptions", ["lease_until"])
    op.create_index("ix_source_subscriptions_last_scan_at", "source_subscriptions", ["last_scan_at"])
    op.create_index("ix_source_subscriptions_last_success_at", "source_subscriptions", ["last_success_at"])
    op.create_index("ix_source_subscriptions_last_changed_at", "source_subscriptions", ["last_changed_at"])
    op.create_index("ix_source_subscriptions_last_outcome", "source_subscriptions", ["last_outcome"])
    op.create_index("ix_source_subscriptions_created_at", "source_subscriptions", ["created_at"])
    _enable_rls("source_subscriptions")

    op.create_table(
        "source_scan_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            sa.String(length=36),
            sa.ForeignKey("source_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column(
            "fetch_id",
            sa.String(length=36),
            sa.ForeignKey("source_fetches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("manual", sa.Boolean(), nullable=False),
        sa.Column("not_modified", sa.Boolean(), nullable=False),
        sa.Column("documents_seen", sa.Integer(), nullable=False),
        sa.Column("documents_created", sa.Integer(), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_scan_runs_organization_id", "source_scan_runs", ["organization_id"])
    op.create_index("ix_source_scan_runs_subscription_id", "source_scan_runs", ["subscription_id"])
    op.create_index("ix_source_scan_runs_outcome", "source_scan_runs", ["outcome"])
    op.create_index("ix_source_scan_runs_fetch_id", "source_scan_runs", ["fetch_id"])
    op.create_index("ix_source_scan_runs_manual", "source_scan_runs", ["manual"])
    op.create_index("ix_source_scan_runs_started_at", "source_scan_runs", ["started_at"])
    op.create_index("ix_source_scan_runs_finished_at", "source_scan_runs", ["finished_at"])
    _enable_rls("source_scan_runs")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "source_scan_runs"')
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "source_subscriptions"')
    op.drop_table("source_scan_runs")
    op.drop_table("source_subscriptions")

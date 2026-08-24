"""add enterprise directory sync ledger

Revision ID: 0017_enterprise_directory_sync
Revises: 0016_pursuit_reminder_deliveries
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_enterprise_directory_sync"
down_revision = "0016_pursuit_reminder_deliveries"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"
TABLES = (
    "directory_sources",
    "directory_role_rules",
    "directory_identity_links",
    "directory_sync_runs",
)


def _enable_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY "{POLICY_NAME}" ON "{table}"
            USING (
                organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
            )
            WITH CHECK (
                organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
            )'''
    )


def upgrade() -> None:
    op.create_table(
        "directory_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="snapshot"),
        sa.Column("default_role", sa.String(length=20), nullable=False, server_default="viewer"),
        sa.Column("authoritative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "code", name="uq_directory_source_org_code"),
    )
    for column in ("organization_id", "code", "provider", "authoritative", "is_active"):
        op.create_index(f"ix_directory_sources_{column}", "directory_sources", [column])

    op.create_table(
        "directory_role_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("directory_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_key", sa.String(length=240), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "source_id", "group_key", name="uq_directory_role_rule_org_source_group"),
    )
    for column in ("organization_id", "source_id", "group_key", "role"):
        op.create_index(f"ix_directory_role_rules_{column}", "directory_role_rules", [column])

    op.create_table(
        "directory_sync_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("directory_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("received_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="applied"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("organization_id", "source_id", "snapshot_sha256", "actor_user_id", "status", "created_at"):
        op.create_index(f"ix_directory_sync_runs_{column}", "directory_sync_runs", [column])

    op.create_table(
        "directory_identity_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("directory_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_subject", sa.String(length=240), nullable=False),
        sa.Column("membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("last_seen_run_id", sa.String(length=36), sa.ForeignKey("directory_sync_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "source_id", "external_subject", name="uq_directory_identity_org_source_subject"),
        sa.UniqueConstraint("organization_id", "membership_id", name="uq_directory_identity_org_membership"),
    )
    for column in ("organization_id", "source_id", "external_subject", "membership_id", "status", "last_seen_run_id", "last_seen_at"):
        op.create_index(f"ix_directory_identity_links_{column}", "directory_identity_links", [column])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TABLES:
            _enable_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in reversed(TABLES):
            op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "{table}"')
    op.drop_table("directory_identity_links")
    op.drop_table("directory_sync_runs")
    op.drop_table("directory_role_rules")
    op.drop_table("directory_sources")

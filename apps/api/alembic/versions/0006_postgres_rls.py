"""add PostgreSQL row level security policies

Revision ID: 0006_postgres_rls
Revises: 0005_tenant_isolation
Create Date: 2026-08-23
"""

from alembic import op

revision = "0006_postgres_rls"
down_revision = "0005_tenant_isolation"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "opportunities",
    "sources",
    "evidence",
    "score_snapshots",
    "opportunity_events",
    "ai_analyses",
    "opportunity_drafts",
    "watch_items",
    "pursuit_actions",
    "pursuit_alerts",
    "audit_logs",
)

POLICY_NAME = "zhituo_tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "{table}"')
        op.execute(
            f'''CREATE POLICY "{POLICY_NAME}" ON "{table}"
                USING (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
                )
                WITH CHECK (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
                )'''
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in reversed(TENANT_TABLES):
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

"""tenant isolation for business data

Revision ID: 0005_tenant_isolation
Revises: 0004_identity_rbac_audit
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_tenant_isolation"
down_revision = "0004_identity_rbac_audit"
branch_labels = None
depends_on = None

LEGACY_ORG_ID = "00000000-0000-0000-0000-000000000001"
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
)


def upgrade() -> None:
    # Existing installations need an explicit holding tenant before organization_id can
    # become NOT NULL. Fresh production installs may leave this tenant unused.
    op.execute(
        sa.text(
            """
            INSERT INTO organizations (id, name, code, is_active, created_at)
            VALUES (:id, 'Legacy Migration Tenant', 'LEGACY-MIGRATION', true, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO NOTHING
            """
        ).bindparams(id=LEGACY_ORG_ID)
    )

    for table in TENANT_TABLES:
        op.add_column(
            table,
            sa.Column(
                "organization_id",
                sa.String(length=36),
                nullable=False,
                server_default=LEGACY_ORG_ID,
            ),
        )
        op.create_foreign_key(
            f"fk_{table}_organization_id",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
        op.alter_column(table, "organization_id", server_default=None)


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_column(table, "organization_id")
    op.execute(sa.text("DELETE FROM organizations WHERE id = :id").bindparams(id=LEGACY_ORG_ID))

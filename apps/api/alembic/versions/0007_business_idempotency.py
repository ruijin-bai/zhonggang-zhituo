"""add database-backed business idempotency records

Revision ID: 0007_business_idempotency
Revises: 0006_postgres_rls
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_business_idempotency"
down_revision = "0006_postgres_rls"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=160), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "scope", "key_hash", name="uq_idempotency_org_scope_key"),
    )
    op.create_index("ix_idempotency_records_organization_id", "idempotency_records", ["organization_id"])
    op.create_index("ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"])
    op.create_index("ix_idempotency_records_status", "idempotency_records", ["status"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "idempotency_records" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY "{POLICY_NAME}" ON "idempotency_records"
                USING (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
                )
                WITH CHECK (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
                )'''
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "idempotency_records"')
    op.drop_table("idempotency_records")

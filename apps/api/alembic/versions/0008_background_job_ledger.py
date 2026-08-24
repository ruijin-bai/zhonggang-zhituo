"""add durable background job ledger

Revision ID: 0008_background_job_ledger
Revises: 0007_business_idempotency
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_background_job_ledger"
down_revision = "0007_business_idempotency"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_type", sa.String(length=120), nullable=False),
        sa.Column("task_name", sa.String(length=160), nullable=False),
        sa.Column("task_args", sa.JSON(), nullable=False),
        sa.Column("resource_id", sa.String(length=160), nullable=True),
        sa.Column("submitted_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_by_email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("retry_of_job_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_background_jobs_organization_id", "background_jobs", ["organization_id"])
    op.create_index("ix_background_jobs_job_type", "background_jobs", ["job_type"])
    op.create_index("ix_background_jobs_resource_id", "background_jobs", ["resource_id"])
    op.create_index("ix_background_jobs_submitted_by_user_id", "background_jobs", ["submitted_by_user_id"])
    op.create_index("ix_background_jobs_status", "background_jobs", ["status"])
    op.create_index("ix_background_jobs_retry_of_job_id", "background_jobs", ["retry_of_job_id"])
    op.create_index("ix_background_jobs_request_id", "background_jobs", ["request_id"])
    op.create_index("ix_background_jobs_correlation_id", "background_jobs", ["correlation_id"])
    op.create_index("ix_background_jobs_submitted_at", "background_jobs", ["submitted_at"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "background_jobs" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY "{POLICY_NAME}" ON "background_jobs"
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
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "background_jobs"')
    op.drop_table("background_jobs")

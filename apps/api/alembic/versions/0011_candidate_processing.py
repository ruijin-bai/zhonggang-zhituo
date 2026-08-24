"""add durable source document candidate processing

Revision ID: 0011_candidate_processing
Revises: 0010_source_subscriptions
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_candidate_processing"
down_revision = "0010_source_subscriptions"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "candidate_processing",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            sa.String(length=36),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "draft_id",
            sa.String(length=36),
            sa.ForeignKey("opportunity_drafts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "duplicate_draft_id",
            sa.String(length=36),
            sa.ForeignKey("opportunity_drafts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("project_detected", sa.Boolean(), nullable=True),
        sa.Column("extraction_mode", sa.String(length=32), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "source_document_id",
            name="uq_candidate_processing_org_source_document",
        ),
    )
    for name, columns in (
        ("ix_candidate_processing_organization_id", ["organization_id"]),
        ("ix_candidate_processing_source_document_id", ["source_document_id"]),
        ("ix_candidate_processing_status", ["status"]),
        ("ix_candidate_processing_draft_id", ["draft_id"]),
        ("ix_candidate_processing_duplicate_draft_id", ["duplicate_draft_id"]),
        ("ix_candidate_processing_project_detected", ["project_detected"]),
        ("ix_candidate_processing_next_attempt_at", ["next_attempt_at"]),
        ("ix_candidate_processing_lease_until", ["lease_until"]),
        ("ix_candidate_processing_created_at", ["created_at"]),
        ("ix_candidate_processing_processed_at", ["processed_at"]),
    ):
        op.create_index(name, "candidate_processing", columns)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "candidate_processing" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY "{POLICY_NAME}" ON "candidate_processing"
                USING (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
                )
                WITH CHECK (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
                )'''
        )

    # Every already archived SourceDocument becomes eligible exactly once. Reusing the source
    # document UUID as the processing id avoids requiring pgcrypto/uuid-ossp during migration.
    op.execute(
        sa.text(
            """
            INSERT INTO candidate_processing (
                id, organization_id, source_document_id, status, attempts,
                next_attempt_at, created_at, updated_at
            )
            SELECT id, organization_id, id, 'pending', 0,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM source_documents
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "candidate_processing"')
    op.drop_table("candidate_processing")

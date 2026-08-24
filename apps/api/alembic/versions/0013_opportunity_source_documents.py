"""link formal opportunities to immutable source documents

Revision ID: 0013_opportunity_source_documents
Revises: 0012_entity_evidence
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_opportunity_source_documents"
down_revision = "0012_entity_evidence"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "opportunity_source_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            sa.String(length=120),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            sa.String(length=36),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "opportunity_id",
            "source_document_id",
            name="uq_opportunity_source_org_opportunity_document",
        ),
    )
    op.create_index(
        "ix_opportunity_source_documents_organization_id",
        "opportunity_source_documents",
        ["organization_id"],
    )
    op.create_index(
        "ix_opportunity_source_documents_opportunity_id",
        "opportunity_source_documents",
        ["opportunity_id"],
    )
    op.create_index(
        "ix_opportunity_source_documents_source_document_id",
        "opportunity_source_documents",
        ["source_document_id"],
    )
    op.create_index(
        "ix_opportunity_source_documents_source_id",
        "opportunity_source_documents",
        ["source_id"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "opportunity_source_documents" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY "{POLICY_NAME}" ON "opportunity_source_documents"
                USING (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
                )
                WITH CHECK (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
                )'''
        )

    # 0012 introduced sources.source_document_id. Backfill any provenance already written during
    # the short interval between the two migrations / rolling deployment steps.
    bind.execute(
        sa.text(
            """
            INSERT INTO opportunity_source_documents (
                organization_id, opportunity_id, source_document_id, source_id, linked_at
            )
            SELECT organization_id, opportunity_id, source_document_id, id, created_at
            FROM sources
            WHERE opportunity_id IS NOT NULL AND source_document_id IS NOT NULL
            ON CONFLICT (organization_id, opportunity_id, source_document_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "opportunity_source_documents"'
        )
    op.drop_table("opportunity_source_documents")

"""add source fetch and normalized document index

Revision ID: 0009_source_document_store
Revises: 0008_background_job_ledger
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_source_document_store"
down_revision = "0008_background_job_ledger"
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
        "source_fetches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("connector", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_url_hash", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_size_bytes", sa.Integer(), nullable=False),
        sa.Column("raw_object_key", sa.String(length=500), nullable=False),
        sa.Column("storage_backend", sa.String(length=20), nullable=False),
        sa.Column("seen_count", sa.Integer(), nullable=False),
        sa.Column("first_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "connector",
            "source_url_hash",
            "raw_sha256",
            name="uq_source_fetch_org_connector_url_raw",
        ),
    )
    op.create_index("ix_source_fetches_organization_id", "source_fetches", ["organization_id"])
    op.create_index("ix_source_fetches_connector", "source_fetches", ["connector"])
    op.create_index("ix_source_fetches_source_url_hash", "source_fetches", ["source_url_hash"])
    op.create_index("ix_source_fetches_raw_sha256", "source_fetches", ["raw_sha256"])
    op.create_index("ix_source_fetches_first_fetched_at", "source_fetches", ["first_fetched_at"])
    op.create_index("ix_source_fetches_last_fetched_at", "source_fetches", ["last_fetched_at"])
    _enable_rls("source_fetches")

    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("connector", sa.String(length=32), nullable=False),
        sa.Column(
            "first_fetch_id",
            sa.String(length=36),
            sa.ForeignKey("source_fetches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "latest_fetch_id",
            sa.String(length=36),
            sa.ForeignKey("source_fetches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("canonical_url_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("publisher", sa.String(length=240), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("text_object_key", sa.String(length=500), nullable=False),
        sa.Column("storage_backend", sa.String(length=20), nullable=False),
        sa.Column("connector_metadata", sa.JSON(), nullable=False),
        sa.Column("seen_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "canonical_url_hash",
            "content_sha256",
            name="uq_source_document_org_url_content",
        ),
    )
    op.create_index("ix_source_documents_organization_id", "source_documents", ["organization_id"])
    op.create_index("ix_source_documents_connector", "source_documents", ["connector"])
    op.create_index("ix_source_documents_first_fetch_id", "source_documents", ["first_fetch_id"])
    op.create_index("ix_source_documents_latest_fetch_id", "source_documents", ["latest_fetch_id"])
    op.create_index("ix_source_documents_canonical_url_hash", "source_documents", ["canonical_url_hash"])
    op.create_index("ix_source_documents_published_at", "source_documents", ["published_at"])
    op.create_index("ix_source_documents_content_sha256", "source_documents", ["content_sha256"])
    op.create_index("ix_source_documents_first_seen_at", "source_documents", ["first_seen_at"])
    op.create_index("ix_source_documents_last_seen_at", "source_documents", ["last_seen_at"])
    _enable_rls("source_documents")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "source_documents"')
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "source_fetches"')
    op.drop_table("source_documents")
    op.drop_table("source_fetches")

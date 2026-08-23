"""add opportunity discovery drafts

Revision ID: 0002_opportunity_drafts
Revises: 0001_initial
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_opportunity_drafts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("discovery", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_title", sa.String(length=500), nullable=False),
        sa.Column("publisher", sa.String(length=240), nullable=False),
        sa.Column("published_at", sa.String(length=40), nullable=False),
        sa.Column("source_rank", sa.String(length=1), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("duplicate_matches", sa.JSON(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_opportunity_drafts_status", "opportunity_drafts", ["status"])
    op.create_index("ix_opportunity_drafts_created_at", "opportunity_drafts", ["created_at"])


def downgrade() -> None:
    op.drop_table("opportunity_drafts")

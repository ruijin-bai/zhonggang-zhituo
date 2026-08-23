"""initial Zhituo market intelligence schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(length=120), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=False),
        sa.Column("sector", sa.String(length=120), nullable=False),
        sa.Column("stage", sa.String(length=120), nullable=False),
        sa.Column("owner", sa.String(length=240), nullable=False),
        sa.Column("estimated_value_usd_m", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(length=1), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("pursuit_thesis", sa.Text(), nullable=False),
        sa.Column("next_actions", sa.JSON(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ["country", "region", "sector", "score", "grade", "decision"]:
        op.create_index(f"ix_opportunities_{column}", "opportunities", [column])

    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("publisher", sa.String(length=240), nullable=False),
        sa.Column("published_at", sa.String(length=40), nullable=False),
        sa.Column("source_rank", sa.String(length=1), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sources_opportunity_id", "sources", ["opportunity_id"])
    op.create_index("ix_sources_source_rank", "sources", ["source_rank"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=True),
        sa.Column("rank", sa.String(length=1), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("publisher", sa.String(length=240), nullable=False),
        sa.Column("published_at", sa.String(length=40), nullable=False),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("field_name", sa.String(length=80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_opportunity_id", "evidence", ["opportunity_id"])
    op.create_index("ix_evidence_source_id", "evidence", ["source_id"])
    op.create_index("ix_evidence_rank", "evidence", ["rank"])
    op.create_index("ix_evidence_field_name", "evidence", ["field_name"])

    op.create_table(
        "score_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(length=1), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
    )
    op.create_index("ix_score_snapshots_opportunity_id", "score_snapshots", ["opportunity_id"])
    op.create_index("ix_score_snapshots_snapshot_at", "score_snapshots", ["snapshot_at"])

    op.create_table(
        "opportunity_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_opportunity_events_opportunity_id", "opportunity_events", ["opportunity_id"])
    op.create_index("ix_opportunity_events_event_type", "opportunity_events", ["event_type"])
    op.create_index("ix_opportunity_events_occurred_at", "opportunity_events", ["occurred_at"])

    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_analyses_opportunity_id", "ai_analyses", ["opportunity_id"])
    op.create_index("ix_ai_analyses_created_at", "ai_analyses", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_analyses")
    op.drop_table("opportunity_events")
    op.drop_table("score_snapshots")
    op.drop_table("evidence")
    op.drop_table("sources")
    op.drop_table("opportunities")

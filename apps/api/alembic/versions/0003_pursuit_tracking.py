"""pursuit tracking tables

Revision ID: 0003_pursuit_tracking
Revises: 0002_opportunity_drafts
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_pursuit_tracking"
down_revision = "0002_opportunity_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watch_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_watch_items_opportunity_id", "watch_items", ["opportunity_id"])
    op.create_index("ix_watch_items_priority", "watch_items", ["priority"])
    op.create_index("ix_watch_items_status", "watch_items", ["status"])
    op.create_index("ix_watch_items_next_review_at", "watch_items", ["next_review_at"])

    op.create_table(
        "pursuit_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pursuit_actions_opportunity_id", "pursuit_actions", ["opportunity_id"])
    op.create_index("ix_pursuit_actions_status", "pursuit_actions", ["status"])
    op.create_index("ix_pursuit_actions_priority", "pursuit_actions", ["priority"])
    op.create_index("ix_pursuit_actions_due_at", "pursuit_actions", ["due_at"])

    op.create_table(
        "pursuit_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("alert_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pursuit_alerts_opportunity_id", "pursuit_alerts", ["opportunity_id"])
    op.create_index("ix_pursuit_alerts_severity", "pursuit_alerts", ["severity"])
    op.create_index("ix_pursuit_alerts_alert_type", "pursuit_alerts", ["alert_type"])
    op.create_index("ix_pursuit_alerts_status", "pursuit_alerts", ["status"])
    op.create_index("ix_pursuit_alerts_created_at", "pursuit_alerts", ["created_at"])


def downgrade() -> None:
    op.drop_table("pursuit_alerts")
    op.drop_table("pursuit_actions")
    op.drop_table("watch_items")

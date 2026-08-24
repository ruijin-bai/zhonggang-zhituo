"""add pursuit reminder and escalation ledger

Revision ID: 0015_pursuit_reminders
Revises: 0014_pursuit_orchestration
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_pursuit_reminders"
down_revision = "0014_pursuit_orchestration"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"


def upgrade() -> None:
    op.add_column(
        "pursuit_work_items",
        sa.Column("blocked_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_pursuit_work_items_blocked_since",
        "pursuit_work_items",
        ["blocked_since"],
    )
    op.execute(
        "UPDATE pursuit_work_items SET blocked_since = updated_at "
        "WHERE status = 'blocked' AND blocked_since IS NULL"
    )

    op.create_table(
        "pursuit_reminders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("pursuit_workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            sa.String(length=120),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_membership_id",
            sa.Integer(),
            sa.ForeignKey("memberships.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "escalated_to_membership_id",
            sa.Integer(),
            sa.ForeignKey("memberships.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "work_item_id",
            sa.String(length=36),
            sa.ForeignKey("pursuit_work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "gate_id",
            sa.String(length=36),
            sa.ForeignKey("pursuit_decision_gates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "review_id",
            sa.String(length=36),
            sa.ForeignKey("pursuit_gate_reviews.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reminder_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("source_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "dedupe_key",
            name="uq_pursuit_reminder_org_dedupe",
        ),
    )

    for column in (
        "organization_id",
        "workspace_id",
        "opportunity_id",
        "recipient_membership_id",
        "escalated_to_membership_id",
        "work_item_id",
        "gate_id",
        "review_id",
        "reminder_type",
        "severity",
        "status",
        "source_due_at",
        "escalation_level",
        "first_triggered_at",
        "last_triggered_at",
        "last_evaluated_at",
    ):
        op.create_index(f"ix_pursuit_reminders_{column}", "pursuit_reminders", [column])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "pursuit_reminders" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY "{POLICY_NAME}" ON "pursuit_reminders"
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
        op.execute(
            f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "pursuit_reminders"'
        )
    op.drop_table("pursuit_reminders")
    op.drop_index("ix_pursuit_work_items_blocked_since", table_name="pursuit_work_items")
    op.drop_column("pursuit_work_items", "blocked_since")

"""add pursuit reminder delivery outbox

Revision ID: 0016_pursuit_reminder_deliveries
Revises: 0015_pursuit_reminders
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_pursuit_reminder_deliveries"
down_revision = "0015_pursuit_reminders"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "pursuit_reminder_deliveries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "reminder_id",
            sa.String(length=36),
            sa.ForeignKey("pursuit_reminders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="email"),
        sa.Column(
            "recipient_membership_id",
            sa.Integer(),
            sa.ForeignKey("memberships.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("recipient_address", sa.String(length=320), nullable=False),
        sa.Column("delivery_key", sa.String(length=220), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "delivery_key",
            name="uq_pursuit_reminder_delivery_org_key",
        ),
    )
    for column in (
        "organization_id",
        "reminder_id",
        "channel",
        "recipient_membership_id",
        "status",
        "next_attempt_at",
        "lease_until",
        "lease_token",
        "created_at",
        "updated_at",
        "sent_at",
    ):
        op.create_index(
            f"ix_pursuit_reminder_deliveries_{column}",
            "pursuit_reminder_deliveries",
            [column],
        )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "pursuit_reminder_deliveries" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY "{POLICY_NAME}" ON "pursuit_reminder_deliveries"
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
            f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "pursuit_reminder_deliveries"'
        )
    op.drop_table("pursuit_reminder_deliveries")

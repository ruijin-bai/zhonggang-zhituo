"""add pursuit orchestration core

Revision ID: 0014_pursuit_orchestration
Revises: 0013_opp_source_docs
Create Date: 2026-08-24
"""

from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0014_pursuit_orchestration"
down_revision = "0013_opp_source_docs"
branch_labels = None
depends_on = None

POLICY_NAME = "zhituo_tenant_isolation"
TABLES = (
    "pursuit_workspaces",
    "pursuit_participants",
    "pursuit_work_items",
    "pursuit_decision_gates",
    "pursuit_gate_reviews",
    "pursuit_decision_records",
)


def _tenant_column() -> sa.Column:
    return sa.Column(
        "organization_id",
        sa.String(length=36),
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )


def _index_many(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "pursuit_workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        _tenant_column(),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("lead_membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "opportunity_id", name="uq_pursuit_workspace_org_opportunity"),
    )
    _index_many("pursuit_workspaces", ("organization_id", "opportunity_id", "status", "priority", "lead_membership_id", "next_review_at", "updated_at"))

    op.create_table(
        "pursuit_participants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _tenant_column(),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("pursuit_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("participant_role", sa.String(length=24), nullable=False, server_default="contributor"),
        sa.Column("responsibility", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "workspace_id", "membership_id", name="uq_pursuit_participant_org_workspace_membership"),
    )
    _index_many("pursuit_participants", ("organization_id", "workspace_id", "membership_id", "participant_role", "status"))

    op.create_table(
        "pursuit_work_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        _tenant_column(),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("pursuit_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_type", sa.String(length=24), nullable=False, server_default="action"),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("assignee_membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True),
        sa.Column("legacy_owner_text", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("dependency_work_item_id", sa.String(length=36), sa.ForeignKey("pursuit_work_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_action_id", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "source_action_id", name="uq_pursuit_work_item_org_legacy_action"),
    )
    _index_many(
        "pursuit_work_items",
        ("organization_id", "workspace_id", "opportunity_id", "assignee_membership_id", "status", "priority", "due_at", "dependency_work_item_id", "source_action_id", "created_at", "updated_at"),
    )

    op.create_table(
        "pursuit_decision_gates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        _tenant_column(),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("pursuit_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gate_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_by_membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    _index_many("pursuit_decision_gates", ("organization_id", "workspace_id", "opportunity_id", "gate_type", "status", "due_at", "opened_at"))

    op.create_table(
        "pursuit_gate_reviews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        _tenant_column(),
        sa.Column("gate_id", sa.String(length=36), sa.ForeignKey("pursuit_decision_gates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_by_membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "gate_id", "reviewer_membership_id", name="uq_pursuit_gate_review_org_gate_reviewer"),
    )
    _index_many("pursuit_gate_reviews", ("organization_id", "gate_id", "reviewer_membership_id", "status", "requested_at"))

    op.create_table(
        "pursuit_decision_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        _tenant_column(),
        sa.Column("gate_id", sa.String(length=36), sa.ForeignKey("pursuit_decision_gates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunity_id", sa.String(length=120), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_by_membership_id", sa.Integer(), sa.ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supersedes_decision_id", sa.String(length=36), sa.ForeignKey("pursuit_decision_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    )
    _index_many("pursuit_decision_records", ("organization_id", "gate_id", "opportunity_id", "decision", "decided_by_membership_id", "supersedes_decision_id", "decided_at"))

    bind = op.get_bind()
    workspace_rows = bind.execute(
        sa.text(
            """
            SELECT DISTINCT o.organization_id, o.id AS opportunity_id,
                   w.priority, w.rationale, w.next_review_at, w.created_at, w.updated_at
            FROM opportunities o
            LEFT JOIN watch_items w
              ON w.organization_id = o.organization_id AND w.opportunity_id = o.id
            WHERE w.id IS NOT NULL
               OR EXISTS (
                    SELECT 1 FROM pursuit_actions a
                    WHERE a.organization_id = o.organization_id AND a.opportunity_id = o.id
               )
            """
        )
    ).mappings().all()

    workspace_ids: dict[tuple[str, str], str] = {}
    migration_now = datetime.now(timezone.utc)
    for row in workspace_rows:
        workspace_id = str(uuid4())
        workspace_ids[(row["organization_id"], row["opportunity_id"])] = workspace_id
        created_at = row["created_at"] or migration_now
        updated_at = row["updated_at"] or created_at
        bind.execute(
            sa.text(
                """
                INSERT INTO pursuit_workspaces (
                    id, organization_id, opportunity_id, status, priority,
                    lead_membership_id, created_by_membership_id, rationale,
                    next_review_at, created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :opportunity_id, 'active', :priority,
                    NULL, NULL, :rationale, :next_review_at, :created_at, :updated_at
                )
                """
            ),
            {
                "id": workspace_id,
                "organization_id": row["organization_id"],
                "opportunity_id": row["opportunity_id"],
                "priority": row["priority"] or "medium",
                "rationale": row["rationale"] or "",
                "next_review_at": row["next_review_at"],
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )

    legacy_actions = bind.execute(
        sa.text(
            """
            SELECT id, organization_id, opportunity_id, title, owner, status,
                   priority, due_at, note, created_at, completed_at
            FROM pursuit_actions
            ORDER BY id ASC
            """
        )
    ).mappings().all()
    for row in legacy_actions:
        workspace_id = workspace_ids.get((row["organization_id"], row["opportunity_id"]))
        if not workspace_id:
            continue
        created_at = row["created_at"] or migration_now
        completed_at = row["completed_at"]
        bind.execute(
            sa.text(
                """
                INSERT INTO pursuit_work_items (
                    id, organization_id, workspace_id, opportunity_id, work_type,
                    title, description, assignee_membership_id, created_by_membership_id,
                    legacy_owner_text, status, priority, due_at, blocked_reason,
                    dependency_work_item_id, source_action_id, completed_at, created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :workspace_id, :opportunity_id, 'action',
                    :title, :description, NULL, NULL, :legacy_owner_text,
                    :status, :priority, :due_at, NULL, NULL, :source_action_id,
                    :completed_at, :created_at, :updated_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "organization_id": row["organization_id"],
                "workspace_id": workspace_id,
                "opportunity_id": row["opportunity_id"],
                "title": row["title"],
                "description": row["note"] or "",
                "legacy_owner_text": row["owner"] or None,
                "status": "done" if row["status"] == "done" else "open",
                "priority": row["priority"] or "medium",
                "due_at": row["due_at"],
                "source_action_id": row["id"],
                "completed_at": completed_at,
                "created_at": created_at,
                "updated_at": completed_at or created_at,
            },
        )

    if bind.dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(
                f'''CREATE POLICY "{POLICY_NAME}" ON "{table}"
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
        for table in reversed(TABLES):
            op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "{table}"')
    for table in reversed(TABLES):
        op.drop_table(table)

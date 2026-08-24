from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

from .db import Base, TenantScopedMixin, utc_now


class PursuitWorkspaceRecord(TenantScopedMixin, Base):
    __tablename__ = "pursuit_workspaces"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "opportunity_id",
            name="uq_pursuit_workspace_org_opportunity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    lead_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rationale: Mapped[str] = mapped_column(Text, default="")
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PursuitParticipantRecord(TenantScopedMixin, Base):
    __tablename__ = "pursuit_participants"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "workspace_id",
            "membership_id",
            name="uq_pursuit_participant_org_workspace_membership",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("pursuit_workspaces.id", ondelete="CASCADE"), index=True
    )
    membership_id: Mapped[int] = mapped_column(
        ForeignKey("memberships.id", ondelete="RESTRICT"), index=True
    )
    participant_role: Mapped[str] = mapped_column(String(24), default="contributor", index=True)
    responsibility: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PursuitWorkItemRecord(TenantScopedMixin, Base):
    __tablename__ = "pursuit_work_items"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_action_id",
            name="uq_pursuit_work_item_org_legacy_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("pursuit_workspaces.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    work_type: Mapped[str] = mapped_column(String(24), default="action", index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    assignee_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    legacy_owner_text: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    dependency_work_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("pursuit_work_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_action_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class PursuitDecisionGateRecord(TenantScopedMixin, Base):
    __tablename__ = "pursuit_decision_gates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("pursuit_workspaces.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    gate_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    opened_by_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PursuitGateReviewRecord(TenantScopedMixin, Base):
    __tablename__ = "pursuit_gate_reviews"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "gate_id",
            "reviewer_membership_id",
            name="uq_pursuit_gate_review_org_gate_reviewer",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    gate_id: Mapped[str] = mapped_column(
        ForeignKey("pursuit_decision_gates.id", ondelete="CASCADE"), index=True
    )
    reviewer_membership_id: Mapped[int] = mapped_column(
        ForeignKey("memberships.id", ondelete="RESTRICT"), index=True
    )
    requested_by_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PursuitDecisionRecord(TenantScopedMixin, Base):
    __tablename__ = "pursuit_decision_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    gate_id: Mapped[str] = mapped_column(
        ForeignKey("pursuit_decision_gates.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(20), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    decided_by_membership_id: Mapped[int] = mapped_column(
        ForeignKey("memberships.id", ondelete="RESTRICT"), index=True
    )
    supersedes_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("pursuit_decision_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


_PURSUIT_TENANT_MODELS = (
    PursuitWorkspaceRecord,
    PursuitParticipantRecord,
    PursuitWorkItemRecord,
    PursuitDecisionGateRecord,
    PursuitGateReviewRecord,
    PursuitDecisionRecord,
)


@event.listens_for(Session, "do_orm_execute")
def _pursuit_tenant_filter(execute_state) -> None:
    organization_id = execute_state.session.info.get("organization_id")
    if not organization_id or not execute_state.is_select:
        return
    statement = execute_state.statement
    for model in _PURSUIT_TENANT_MODELS:
        statement = statement.options(
            with_loader_criteria(
                model,
                model.organization_id == organization_id,
                include_aliases=True,
            )
        )
    execute_state.statement = statement

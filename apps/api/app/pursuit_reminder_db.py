from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

from .db import Base, TenantScopedMixin, utc_now


class PursuitReminderRecord(TenantScopedMixin, Base):
    __tablename__ = "pursuit_reminders"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "dedupe_key",
            name="uq_pursuit_reminder_org_dedupe",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("pursuit_workspaces.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    recipient_membership_id: Mapped[int] = mapped_column(
        ForeignKey("memberships.id", ondelete="RESTRICT"), index=True
    )
    escalated_to_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    work_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("pursuit_work_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    gate_id: Mapped[str | None] = mapped_column(
        ForeignKey("pursuit_decision_gates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    review_id: Mapped[str | None] = mapped_column(
        ForeignKey("pursuit_gate_reviews.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reminder_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(160))
    source_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    first_triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    last_triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    last_evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@event.listens_for(Session, "do_orm_execute")
def _pursuit_reminder_tenant_filter(execute_state) -> None:
    organization_id = execute_state.session.info.get("organization_id")
    if not organization_id or not execute_state.is_select:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            PursuitReminderRecord,
            PursuitReminderRecord.organization_id == organization_id,
            include_aliases=True,
        )
    )

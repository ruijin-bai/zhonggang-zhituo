from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

from .db import Base, TenantScopedMixin, utc_now


class PursuitReminderDeliveryRecord(TenantScopedMixin, Base):
    __tablename__ = "pursuit_reminder_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "delivery_key",
            name="uq_pursuit_reminder_delivery_org_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reminder_id: Mapped[str] = mapped_column(
        ForeignKey("pursuit_reminders.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(20), default="email", index=True)
    recipient_membership_id: Mapped[int] = mapped_column(
        ForeignKey("memberships.id", ondelete="RESTRICT"), index=True
    )
    recipient_address: Mapped[str] = mapped_column(String(320))
    delivery_key: Mapped[str] = mapped_column(String(220))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


@event.listens_for(Session, "do_orm_execute")
def _pursuit_delivery_tenant_filter(execute_state) -> None:
    organization_id = execute_state.session.info.get("organization_id")
    if not organization_id or not execute_state.is_select:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            PursuitReminderDeliveryRecord,
            PursuitReminderDeliveryRecord.organization_id == organization_id,
            include_aliases=True,
        )
    )

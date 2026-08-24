from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

from .db import Base, TenantScopedMixin, utc_now


class OpportunitySourceDocumentRecord(TenantScopedMixin, Base):
    __tablename__ = "opportunity_source_documents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "opportunity_id",
            "source_document_id",
            name="uq_opportunity_source_org_opportunity_document",
        ),
        UniqueConstraint(
            "organization_id",
            "source_document_id",
            name="uq_opportunity_source_org_document",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(Session, "do_orm_execute")
def _opportunity_source_tenant_filter(execute_state) -> None:
    organization_id = execute_state.session.info.get("organization_id")
    if not organization_id or not execute_state.is_select:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            OpportunitySourceDocumentRecord,
            OpportunitySourceDocumentRecord.organization_id == organization_id,
            include_aliases=True,
        )
    )

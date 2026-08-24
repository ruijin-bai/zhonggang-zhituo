from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

from .db import Base, TenantScopedMixin, utc_now


class CandidateProcessingRecord(TenantScopedMixin, Base):
    """Durable one-to-one processing state for a normalized SourceDocument."""

    __tablename__ = "candidate_processing"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_document_id",
            name="uq_candidate_processing_org_source_document",
        ),
    )

    # Use the source document UUID as the processing id. This makes migration backfill possible
    # without requiring a database UUID extension and preserves the one-document/one-processing
    # invariant explicitly.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    duplicate_draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_detected: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    extraction_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


@event.listens_for(Session, "do_orm_execute")
def _candidate_tenant_filter(execute_state) -> None:
    organization_id = execute_state.session.info.get("organization_id")
    if not organization_id or not execute_state.is_select:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            CandidateProcessingRecord,
            CandidateProcessingRecord.organization_id == organization_id,
            include_aliases=True,
        )
    )

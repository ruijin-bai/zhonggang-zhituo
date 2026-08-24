from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

from .db import Base, TenantScopedMixin, utc_now


class SourceDocumentInsightRecord(TenantScopedMixin, Base):
    __tablename__ = "source_document_insights"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), unique=True, index=True
    )
    project_detected: Mapped[bool] = mapped_column(Boolean, index=True)
    extraction_mode: Mapped[str] = mapped_column(String(40))
    discovery: Mapped[dict] = mapped_column(JSON)
    identity_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class CandidateSourceDocumentRecord(TenantScopedMixin, Base):
    __tablename__ = "candidate_source_documents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "draft_id",
            "source_document_id",
            name="uq_candidate_source_org_draft_document",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("opportunity_drafts.id", ondelete="CASCADE"), index=True
    )
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EntityRecord(TenantScopedMixin, Base):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "identity_key",
            name="uq_entity_org_type_identity",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    canonical_name: Mapped[str] = mapped_column(String(320))
    normalized_name: Mapped[str] = mapped_column(String(320), index=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_key: Mapped[str] = mapped_column(String(120), default="", index=True)
    identity_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    entity_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class EntityAliasRecord(TenantScopedMixin, Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_id",
            "normalized_alias",
            name="uq_entity_alias_org_entity_normalized",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(320))
    normalized_alias: Mapped[str] = mapped_column(String(320), index=True)
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SourceEntityMentionRecord(TenantScopedMixin, Base):
    __tablename__ = "source_entity_mentions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_document_id",
            "entity_id",
            "role",
            name="uq_entity_mention_org_document_entity_role",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    name_text: Mapped[str] = mapped_column(String(320))
    evidence_quote: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    resolver: Mapped[str] = mapped_column(String(40), default="exact")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OpportunityEntityLinkRecord(TenantScopedMixin, Base):
    __tablename__ = "opportunity_entity_links"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "opportunity_id",
            "entity_id",
            "role",
            name="uq_opportunity_entity_org_opportunity_entity_role",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


INTELLIGENCE_TENANT_MODELS = (
    SourceDocumentInsightRecord,
    CandidateSourceDocumentRecord,
    EntityRecord,
    EntityAliasRecord,
    SourceEntityMentionRecord,
    OpportunityEntityLinkRecord,
)


@event.listens_for(Session, "do_orm_execute")
def _intelligence_tenant_filter(execute_state) -> None:
    organization_id = execute_state.session.info.get("organization_id")
    if not organization_id or not execute_state.is_select:
        return
    statement = execute_state.statement
    for model in INTELLIGENCE_TENANT_MODELS:
        statement = statement.options(
            with_loader_criteria(
                model,
                model.organization_id == organization_id,
                include_aliases=True,
            )
        )
    execute_state.statement = statement

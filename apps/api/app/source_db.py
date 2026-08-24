from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

from .db import Base, TenantScopedMixin, utc_now


class SourceFetchRecord(TenantScopedMixin, Base):
    """One distinct raw representation of a source URL, observed one or more times."""

    __tablename__ = "source_fetches"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connector",
            "source_url_hash",
            "raw_sha256",
            name="uq_source_fetch_org_connector_url_raw",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector: Mapped[str] = mapped_column(String(32), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    source_url_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_type: Mapped[str] = mapped_column(String(160))
    raw_sha256: Mapped[str] = mapped_column(String(64), index=True)
    raw_size_bytes: Mapped[int] = mapped_column(Integer)
    raw_object_key: Mapped[str] = mapped_column(String(500))
    storage_backend: Mapped[str] = mapped_column(String(20))
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    first_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    last_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class SourceDocumentRecord(TenantScopedMixin, Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "canonical_url_hash",
            "content_sha256",
            name="uq_source_document_org_url_content",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector: Mapped[str] = mapped_column(String(32), index=True)
    first_fetch_id: Mapped[str] = mapped_column(
        ForeignKey("source_fetches.id", ondelete="RESTRICT"),
        index=True,
    )
    latest_fetch_id: Mapped[str] = mapped_column(
        ForeignKey("source_fetches.id", ondelete="RESTRICT"),
        index=True,
    )
    canonical_url: Mapped[str] = mapped_column(Text)
    canonical_url_hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(500))
    publisher: Mapped[str | None] = mapped_column(String(240), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    content_type: Mapped[str] = mapped_column(String(160))
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    text_object_key: Mapped[str] = mapped_column(String(500))
    storage_backend: Mapped[str] = mapped_column(String(20))
    connector_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class SourceSubscriptionRecord(TenantScopedMixin, Base):
    __tablename__ = "source_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connector",
            "url_hash",
            name="uq_source_subscription_org_connector_url",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(240))
    connector: Mapped[str] = mapped_column(String(32), index=True)
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    pause_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    interval_seconds: Mapped[int] = mapped_column(Integer)
    next_scan_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    etag: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(500), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    total_scans: Mapped[int] = mapped_column(Integer, default=0)
    total_changes: Mapped[int] = mapped_column(Integer, default=0)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_outcome: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class SourceScanRunRecord(TenantScopedMixin, Base):
    __tablename__ = "source_scan_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("source_subscriptions.id", ondelete="CASCADE"),
        index=True,
    )
    outcome: Mapped[str] = mapped_column(String(40), index=True)
    fetch_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_fetches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    manual: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    not_modified: Mapped[bool] = mapped_column(Boolean, default=False)
    documents_seen: Mapped[int] = mapped_column(Integer, default=0)
    documents_created: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


_SOURCE_TENANT_MODELS = (
    SourceFetchRecord,
    SourceDocumentRecord,
    SourceSubscriptionRecord,
    SourceScanRunRecord,
)


@event.listens_for(Session, "do_orm_execute")
def _source_tenant_filter(execute_state) -> None:
    organization_id = execute_state.session.info.get("organization_id")
    if not organization_id or not execute_state.is_select:
        return
    statement = execute_state.statement
    for model in _SOURCE_TENANT_MODELS:
        statement = statement.options(
            with_loader_criteria(
                model,
                model.organization_id == organization_id,
                include_aliases=True,
            )
        )
    execute_state.statement = statement

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

from .db import Base, TenantScopedMixin, utc_now


class DirectorySourceRecord(TenantScopedMixin, Base):
    __tablename__ = "directory_sources"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_directory_source_org_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(240))
    provider: Mapped[str] = mapped_column(String(40), default="snapshot", index=True)
    default_role: Mapped[str] = mapped_column(String(20), default="viewer")
    authoritative: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DirectoryRoleRuleRecord(TenantScopedMixin, Base):
    __tablename__ = "directory_role_rules"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_id",
            "group_key",
            name="uq_directory_role_rule_org_source_group",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("directory_sources.id", ondelete="CASCADE"), index=True
    )
    group_key: Mapped[str] = mapped_column(String(240), index=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DirectorySyncRunRecord(TenantScopedMixin, Base):
    __tablename__ = "directory_sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("directory_sources.id", ondelete="CASCADE"), index=True
    )
    snapshot_sha256: Mapped[str] = mapped_column(String(64), index=True)
    received_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="applied", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DirectoryIdentityLinkRecord(TenantScopedMixin, Base):
    __tablename__ = "directory_identity_links"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_id",
            "external_subject",
            name="uq_directory_identity_org_source_subject",
        ),
        UniqueConstraint(
            "organization_id",
            "membership_id",
            name="uq_directory_identity_org_membership",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("directory_sources.id", ondelete="CASCADE"), index=True
    )
    external_subject: Mapped[str] = mapped_column(String(240), index=True)
    membership_id: Mapped[int] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    last_seen_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("directory_sync_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


_DIRECTORY_TENANT_MODELS = (
    DirectorySourceRecord,
    DirectoryRoleRuleRecord,
    DirectoryIdentityLinkRecord,
    DirectorySyncRunRecord,
)


@event.listens_for(Session, "do_orm_execute")
def _directory_tenant_filter(execute_state) -> None:
    organization_id = execute_state.session.info.get("organization_id")
    if not organization_id or not execute_state.is_select:
        return
    statement = execute_state.statement
    for model in _DIRECTORY_TENANT_MODELS:
        statement = statement.options(
            with_loader_criteria(
                model,
                model.organization_id == organization_id,
                include_aliases=True,
            )
        )
    execute_state.statement = statement

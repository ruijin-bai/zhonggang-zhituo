from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class OpportunityRecord(Base):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    country: Mapped[str] = mapped_column(String(120), index=True)
    region: Mapped[str] = mapped_column(String(120), index=True)
    sector: Mapped[str] = mapped_column(String(120), index=True)
    stage: Mapped[str] = mapped_column(String(120))
    owner: Mapped[str] = mapped_column(String(240))
    estimated_value_usd_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, index=True)
    grade: Mapped[str] = mapped_column(String(1), index=True)
    confidence: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(40), index=True)
    breakdown: Mapped[dict] = mapped_column(JSON)
    pursuit_thesis: Mapped[str] = mapped_column(Text)
    next_actions: Mapped[list] = mapped_column(JSON, default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class SourceRecord(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    publisher: Mapped[str] = mapped_column(String(240))
    published_at: Mapped[str] = mapped_column(String(40))
    source_rank: Mapped[str] = mapped_column(String(1), index=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvidenceRecord(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=True, index=True)
    rank: Mapped[str] = mapped_column(String(1), index=True)
    title: Mapped[str] = mapped_column(String(500))
    publisher: Mapped[str] = mapped_column(String(240))
    published_at: Mapped[str] = mapped_column(String(40))
    fact: Mapped[str] = mapped_column(Text)
    field_name: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ScoreSnapshotRecord(Base):
    __tablename__ = "score_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    total: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(1))
    breakdown: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text)


class OpportunityEventRecord(Base):
    __tablename__ = "opportunity_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class AIAnalysisRecord(Base):
    __tablename__ = "ai_analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class OpportunityDraftRecord(Base):
    __tablename__ = "opportunity_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    discovery: Mapped[dict] = mapped_column(JSON)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_title: Mapped[str] = mapped_column(String(500))
    publisher: Mapped[str] = mapped_column(String(240))
    published_at: Mapped[str] = mapped_column(String(40))
    source_rank: Mapped[str] = mapped_column(String(1))
    raw_text: Mapped[str] = mapped_column(Text)
    duplicate_matches: Mapped[list] = mapped_column(JSON, default=list)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

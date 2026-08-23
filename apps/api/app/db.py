from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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
    score: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(1), index=True)
    confidence: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(40))
    breakdown: Mapped[dict] = mapped_column(JSON)
    pursuit_thesis: Mapped[str] = mapped_column(Text)
    next_actions: Mapped[list] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class EvidenceRecord(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    rank: Mapped[str] = mapped_column(String(1))
    title: Mapped[str] = mapped_column(String(300))
    publisher: Mapped[str] = mapped_column(String(240))
    published_at: Mapped[str] = mapped_column(String(40))
    fact: Mapped[str] = mapped_column(Text)

class ScoreSnapshotRecord(Base):
    __tablename__ = "score_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    total: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(1))
    breakdown: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text)

class OpportunityEventRecord(Base):
    __tablename__ = "opportunity_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    payload: Mapped[dict] = mapped_column(JSON)

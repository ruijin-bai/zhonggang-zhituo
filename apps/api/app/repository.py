import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_settings
from .db import EvidenceRecord, OpportunityRecord, ScoreSnapshotRecord
from .models import Evidence, Opportunity, ScoreSnapshot

DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "demo" / "opportunities.json"
settings = get_settings()


@lru_cache(maxsize=1)
def load_demo_opportunities() -> list[Opportunity]:
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return [Opportunity.model_validate(item) for item in payload]


def _from_record(record: OpportunityRecord, session: Session) -> Opportunity:
    evidence_records = session.scalars(
        select(EvidenceRecord)
        .where(EvidenceRecord.opportunity_id == record.id)
        .order_by(EvidenceRecord.created_at.asc())
    ).all()
    snapshot_records = session.scalars(
        select(ScoreSnapshotRecord)
        .where(ScoreSnapshotRecord.opportunity_id == record.id)
        .order_by(ScoreSnapshotRecord.snapshot_at.asc())
    ).all()

    evidence = [
        Evidence(
            id=item.id,
            rank=item.rank,
            title=item.title,
            publisher=item.publisher,
            published_at=item.published_at,
            fact=item.fact,
            field_name=item.field_name,
            confidence=item.confidence,
            source_url=item.source_url,
        )
        for item in evidence_records
    ]
    history = [
        ScoreSnapshot(
            date=item.snapshot_at.date().isoformat(),
            total=item.total,
            grade=item.grade,
            note=item.note,
        )
        for item in snapshot_records
    ]
    return Opportunity(
        id=record.id,
        title=record.title,
        country=record.country,
        region=record.region,
        sector=record.sector,
        stage=record.stage,
        owner=record.owner,
        estimated_value_usd_m=record.estimated_value_usd_m,
        summary=record.summary,
        score=record.score,
        grade=record.grade,
        confidence=record.confidence,
        decision=record.decision,
        breakdown=record.breakdown,
        evidence=evidence,
        score_history=history,
        pursuit_thesis=record.pursuit_thesis,
        next_actions=record.next_actions or [],
        is_demo=record.is_demo,
    )


def list_opportunities(session: Session) -> list[Opportunity]:
    if settings.data_backend != "json":
        try:
            records = session.scalars(
                select(OpportunityRecord).order_by(OpportunityRecord.score.desc())
            ).all()
            if records:
                return [_from_record(record, session) for record in records]
        except SQLAlchemyError:
            if settings.data_backend == "database":
                raise
    return load_demo_opportunities()


def get_opportunity(opportunity_id: str, session: Session) -> Opportunity | None:
    if settings.data_backend != "json":
        try:
            record = session.get(OpportunityRecord, opportunity_id)
            if record is not None:
                return _from_record(record, session)
        except SQLAlchemyError:
            if settings.data_backend == "database":
                raise
    return next(
        (item for item in load_demo_opportunities() if item.id == opportunity_id),
        None,
    )


def database_record(opportunity_id: str, session: Session) -> OpportunityRecord | None:
    if settings.data_backend == "json":
        return None
    try:
        return session.get(OpportunityRecord, opportunity_id)
    except SQLAlchemyError:
        if settings.data_backend == "database":
            raise
        return None

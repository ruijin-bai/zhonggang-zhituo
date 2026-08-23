import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import EvidenceRecord, OpportunityRecord, ScoreSnapshotRecord
from .models import Opportunity

DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "demo" / "opportunities.json"


def seed_demo_data(session: Session) -> int:
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    created = 0
    for raw in payload:
        item = Opportunity.model_validate(raw)
        existing = session.get(OpportunityRecord, item.id)
        if existing is not None:
            continue
        record = OpportunityRecord(
            id=item.id,
            title=item.title,
            country=item.country,
            region=item.region,
            sector=item.sector,
            stage=item.stage,
            owner=item.owner,
            estimated_value_usd_m=item.estimated_value_usd_m,
            summary=item.summary,
            score=item.score,
            grade=item.grade,
            confidence=item.confidence,
            decision=item.decision,
            breakdown=item.breakdown.model_dump(),
            pursuit_thesis=item.pursuit_thesis,
            next_actions=item.next_actions,
            is_demo=True,
        )
        session.add(record)
        session.flush()
        for evidence in item.evidence:
            session.add(
                EvidenceRecord(
                    id=evidence.id or str(uuid4()),
                    opportunity_id=item.id,
                    source_id=None,
                    rank=evidence.rank,
                    title=evidence.title,
                    publisher=evidence.publisher,
                    published_at=evidence.published_at,
                    fact=evidence.fact,
                    field_name=evidence.field_name,
                    confidence=evidence.confidence,
                    source_url=evidence.source_url,
                )
            )
        for snapshot in item.score_history:
            session.add(
                ScoreSnapshotRecord(
                    opportunity_id=item.id,
                    total=snapshot.total,
                    grade=snapshot.grade,
                    breakdown=item.breakdown.model_dump(),
                    note=snapshot.note,
                )
            )
        created += 1
    session.commit()
    return created

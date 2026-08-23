import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from .db import EvidenceRecord, OpportunityRecord, ScoreSnapshotRecord
from .models import Opportunity, ScoreBreakdown
from .scoring import calculate_score

DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "demo" / "opportunities.json"
HERO_ID = "west-africa-port-access-corridor"


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def seed_demo_data(session: Session) -> int:
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    created = 0
    for raw in payload:
        item = Opportunity.model_validate(raw)
        if session.get(OpportunityRecord, item.id) is not None:
            continue

        breakdown = item.breakdown
        score = item.score
        grade = item.grade
        decision = item.decision
        stage = item.stage
        seed_evidence = item.evidence
        seed_history = item.score_history

        # The persistent hero starts BEFORE the financing/procurement event so the
        # workbench can truly demonstrate 72/B -> 81/A after source ingestion.
        if item.id == HERO_ID:
            breakdown = ScoreBreakdown(
                strategic_fit=18,
                project_maturity=11,
                financing=8,
                client_quality=8,
                capability_fit=13,
                local_position=7,
                competition=4,
                risk_control=3,
            )
            score_result = calculate_score(breakdown, item.confidence)
            score = score_result.total
            grade = score_result.grade
            decision = score_result.decision
            stage = "融资谈判与采购前期"
            seed_evidence = []
            seed_history = [item.score_history[0]]

        record = OpportunityRecord(
            id=item.id,
            title=item.title,
            country=item.country,
            region=item.region,
            sector=item.sector,
            stage=stage,
            owner=item.owner,
            estimated_value_usd_m=item.estimated_value_usd_m,
            summary=item.summary,
            score=score,
            grade=grade,
            confidence=item.confidence,
            decision=decision,
            breakdown=breakdown.model_dump(),
            pursuit_thesis=item.pursuit_thesis,
            next_actions=item.next_actions,
            is_demo=True,
        )
        session.add(record)
        session.flush()

        for evidence in seed_evidence:
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

        for snapshot in seed_history:
            snapshot_breakdown = breakdown.model_dump()
            session.add(
                ScoreSnapshotRecord(
                    opportunity_id=item.id,
                    snapshot_at=_date(snapshot.date),
                    total=snapshot.total,
                    grade=snapshot.grade,
                    breakdown=snapshot_breakdown,
                    note=snapshot.note,
                )
            )
        created += 1

    session.commit()
    return created

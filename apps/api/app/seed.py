import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import EvidenceRecord, OpportunityRecord, PursuitActionRecord, ScoreSnapshotRecord, WatchItemRecord
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

        if item.id == HERO_ID:
            breakdown = ScoreBreakdown(strategic_fit=18, project_maturity=11, financing=8, client_quality=8, capability_fit=13, local_position=7, competition=4, risk_control=3)
            score_result = calculate_score(breakdown, item.confidence)
            score = score_result.total
            grade = score_result.grade
            decision = score_result.decision
            stage = "融资谈判与采购前期"
            seed_evidence = []
            seed_history = [item.score_history[0]]

        record = OpportunityRecord(id=item.id, title=item.title, country=item.country, region=item.region, sector=item.sector, stage=stage, owner=item.owner, estimated_value_usd_m=item.estimated_value_usd_m, summary=item.summary, score=score, grade=grade, confidence=item.confidence, decision=decision, breakdown=breakdown.model_dump(), pursuit_thesis=item.pursuit_thesis, next_actions=item.next_actions, is_demo=True)
        session.add(record)
        session.flush()

        for evidence in seed_evidence:
            session.add(EvidenceRecord(id=evidence.id or str(uuid4()), opportunity_id=item.id, source_id=None, rank=evidence.rank, title=evidence.title, publisher=evidence.publisher, published_at=evidence.published_at, fact=evidence.fact, field_name=evidence.field_name, confidence=evidence.confidence, source_url=evidence.source_url))

        for snapshot in seed_history:
            session.add(ScoreSnapshotRecord(opportunity_id=item.id, snapshot_at=_date(snapshot.date), total=snapshot.total, grade=snapshot.grade, breakdown=breakdown.model_dump(), note=snapshot.note))
        created += 1

    # Seed a realistic pursuit workspace once the tracking migration is available.
    hero = session.get(OpportunityRecord, HERO_ID)
    if hero and session.scalar(select(WatchItemRecord).where(WatchItemRecord.opportunity_id == HERO_ID)) is None:
        now = datetime.now(timezone.utc)
        session.add(WatchItemRecord(opportunity_id=HERO_ID, priority="high", owner="市场经营负责人", rationale="港航及交通能力匹配，融资与采购窗口值得重点跟踪。", next_review_at=now + timedelta(days=7)))
        session.add(PursuitActionRecord(opportunity_id=HERO_ID, title="核实采购模式与预计招标时间", owner="市场经理", priority="high", due_at=now + timedelta(days=5), note="重点确认 EPC/DB/传统招标路径及资格预审时间。"))
        session.add(PursuitActionRecord(opportunity_id=HERO_ID, title="梳理业主与融资方决策链", owner="区域团队", priority="high", due_at=now + timedelta(days=8), note="只记录可验证机构和正式角色，不推测私人关系。"))
        session.add(PursuitActionRecord(opportunity_id=HERO_ID, title="准备同类业绩与属地资源证明", owner="投标支持", priority="medium", due_at=now + timedelta(days=12), note="形成可直接用于经营沟通的能力材料包。"))

    session.commit()
    return created

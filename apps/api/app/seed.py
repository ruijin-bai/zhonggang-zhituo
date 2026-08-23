import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import (
    AIAnalysisRecord,
    EvidenceRecord,
    MembershipRecord,
    OpportunityDraftRecord,
    OpportunityEventRecord,
    OpportunityRecord,
    OrganizationRecord,
    PursuitActionRecord,
    PursuitAlertRecord,
    ScoreSnapshotRecord,
    SourceRecord,
    UserRecord,
    WatchItemRecord,
)
from .models import Opportunity, ScoreBreakdown
from .scoring import calculate_score

DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "demo" / "opportunities.json"
HERO_ID = "west-africa-port-access-corridor"


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _seed_identity(session: Session) -> str:
    org = session.scalar(select(OrganizationRecord).where(OrganizationRecord.code == "CHEC-DEMO"))
    if org is None:
        org = OrganizationRecord(id=str(uuid4()), name="中港智拓演示组织", code="CHEC-DEMO", is_active=True)
        session.add(org)
        session.flush()
    user = session.scalar(select(UserRecord).where(UserRecord.email == "admin@zhituo.local"))
    if user is None:
        user = UserRecord(id=str(uuid4()), email="admin@zhituo.local", display_name="智拓管理员", is_active=True)
        session.add(user)
        session.flush()
    membership = session.scalar(
        select(MembershipRecord).where(
            MembershipRecord.organization_id == org.id,
            MembershipRecord.user_id == user.id,
        )
    )
    if membership is None:
        session.add(MembershipRecord(organization_id=org.id, user_id=user.id, role="admin", is_active=True))
    session.flush()
    return org.id


def reset_demo_data(session: Session) -> int:
    """Delete demo business data only, preserving all non-demo/public records and identities."""
    previous_org = session.info.pop("organization_id", None)
    try:
        demo_ids = list(session.scalars(select(OpportunityRecord.id).where(OpportunityRecord.is_demo.is_(True))).all())
        if demo_ids:
            for model in (
                AIAnalysisRecord,
                PursuitAlertRecord,
                PursuitActionRecord,
                WatchItemRecord,
                OpportunityEventRecord,
                ScoreSnapshotRecord,
                EvidenceRecord,
                SourceRecord,
            ):
                session.execute(delete(model).where(model.opportunity_id.in_(demo_ids)))
            session.execute(delete(OpportunityRecord).where(OpportunityRecord.id.in_(demo_ids)))
        session.execute(delete(OpportunityDraftRecord).where(OpportunityDraftRecord.is_demo.is_(True)))
        session.commit()
        return len(demo_ids)
    finally:
        if previous_org:
            session.info["organization_id"] = previous_org


def seed_demo_data(session: Session) -> int:
    """Seed demo data without leaking the demo tenant into the caller's Session context."""
    previous_org = session.info.pop("organization_id", None)
    try:
        org_id = _seed_identity(session)
        session.info["organization_id"] = org_id
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
                result = calculate_score(breakdown, item.confidence)
                score = result.total
                grade = result.grade
                decision = result.decision
                stage = "融资谈判与采购前期"
                seed_evidence = []
                seed_history = [item.score_history[0]]
            session.add(
                OpportunityRecord(
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
            )
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
                session.add(
                    ScoreSnapshotRecord(
                        opportunity_id=item.id,
                        snapshot_at=_date(snapshot.date),
                        total=snapshot.total,
                        grade=snapshot.grade,
                        breakdown=breakdown.model_dump(),
                        note=snapshot.note,
                    )
                )
            created += 1

        hero = session.get(OpportunityRecord, HERO_ID)
        if hero and session.scalar(select(WatchItemRecord).where(WatchItemRecord.opportunity_id == HERO_ID)) is None:
            now = datetime.now(timezone.utc)
            session.add(
                WatchItemRecord(
                    opportunity_id=HERO_ID,
                    priority="high",
                    owner="市场经营负责人",
                    rationale="港航及交通能力匹配，融资与采购窗口值得重点跟踪。",
                    next_review_at=now + timedelta(days=7),
                )
            )
            session.add_all(
                [
                    PursuitActionRecord(opportunity_id=HERO_ID, title="核实采购模式与预计招标时间", owner="市场经理", priority="high", due_at=now + timedelta(days=5), note="确认采购路径及资格预审时间。"),
                    PursuitActionRecord(opportunity_id=HERO_ID, title="梳理业主与融资方决策链", owner="区域团队", priority="high", due_at=now + timedelta(days=8), note="只记录可验证机构和正式角色。"),
                    PursuitActionRecord(opportunity_id=HERO_ID, title="形成港口+疏港交通一体化方案摘要", owner="技术经营组", priority="high", due_at=now + timedelta(days=10), note="把综合交付能力转化为客户价值。"),
                ]
            )
            v1 = {
                "win_theme": "依托港航与交通综合能力参与项目经营，重点验证融资与采购窗口。",
                "client_need": "提升港区集疏运效率并形成可实施的交通基础设施方案。",
                "differentiation": ["港航工程与道路交通综合实施能力"],
                "gaps": ["融资落实程度待核实", "客户决策链待补充", "竞争格局待核实"],
                "competitors": [],
                "stakeholders": [],
                "next_moves": ["核实采购模式与预计招标时间", "梳理业主与融资方决策链"],
                "updated_at": (now - timedelta(days=6)).isoformat(),
            }
            v2 = {
                "win_theme": "以港口—疏港交通一体化交付能力，帮助业主降低多接口协调风险并提升项目落地确定性。",
                "client_need": "在融资与采购尚处前期时，尽快形成可融资、可采购、可实施的一体化建设路径。",
                "differentiation": ["港航+道路交通跨专业一体化组织能力", "海外属地供应链和施工资源可支撑快速落地", "同类大型基础设施履约经验可降低接口与工期风险"],
                "gaps": ["采购评价权重尚无正式证据", "融资方对实施方案的核心约束待核实"],
                "competitors": [],
                "stakeholders": [
                    {"name": "业主项目执行机构", "organization": "项目业主", "role": "项目决策与采购组织", "influence": "high", "stance": "unknown", "evidence": "公开项目组织信息，具体人员待核实", "confidence": 65},
                    {"name": "融资机构项目团队", "organization": "融资方", "role": "融资条件与项目可实施性审查", "influence": "high", "stance": "unknown", "evidence": "融资谈判阶段判断，具体机构要求待正式来源确认", "confidence": 55},
                ],
                "next_moves": ["核实采购模式与预计招标时间", "形成港口+疏港交通一体化方案摘要", "获取融资约束与采购评价标准的一手信息"],
                "updated_at": now.isoformat(),
            }
            session.add(OpportunityEventRecord(opportunity_id=HERO_ID, event_type="strategy_updated", occurred_at=now - timedelta(days=6), payload=v1))
            session.add(OpportunityEventRecord(opportunity_id=HERO_ID, event_type="strategy_updated", occurred_at=now, payload=v2))
        session.commit()
        return created
    finally:
        session.info.pop("organization_id", None)
        if previous_org:
            session.info["organization_id"] = previous_org

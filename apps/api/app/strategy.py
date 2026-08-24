from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import OpportunityEventRecord, OpportunityRecord, PursuitActionRecord
from .repository import get_opportunity


class StrategyVersionConflict(ValueError):
    def __init__(self, expected_version: int, current_version: int):
        super().__init__(
            f"策略版本冲突：提交基于 V{expected_version}，当前已经是 V{current_version}。请刷新后合并最新修改。"
        )
        self.expected_version = expected_version
        self.current_version = current_version


class CompetitorInput(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    position: str = "待核实"
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: str = ""
    confidence: int = Field(default=50, ge=0, le=100)


class StakeholderInput(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    organization: str = "待核实"
    role: str = "待核实"
    influence: str = "medium"
    stance: str = "unknown"
    evidence: str = ""
    confidence: int = Field(default=50, ge=0, le=100)


class StrategyUpsert(BaseModel):
    # Clients must submit the version returned by GET. V0 means no persisted strategy yet.
    expected_version: int = Field(ge=0)
    win_theme: str = ""
    client_need: str = ""
    differentiation: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    competitors: list[CompetitorInput] = Field(default_factory=list)
    stakeholders: list[StakeholderInput] = Field(default_factory=list)
    next_moves: list[str] = Field(default_factory=list)


class StrategyWorkspace(BaseModel):
    opportunity: dict
    strategy: dict
    version: int = Field(ge=0)
    readiness: int = Field(ge=0, le=100)
    readiness_label: str
    evidence_warnings: list[str]

    @property
    def etag(self) -> str:
        return f'"strategy-{self.version}"'


def _default_strategy(opportunity) -> dict:
    return {
        "win_theme": opportunity.pursuit_thesis,
        "client_need": opportunity.summary,
        "differentiation": [],
        "gaps": ["竞争格局待补充", "客户决策链待核实"],
        "competitors": [],
        "stakeholders": [],
        "next_moves": opportunity.next_actions,
        "updated_at": None,
    }


def _readiness(strategy: dict) -> tuple[int, list[str]]:
    score = 0
    warnings: list[str] = []
    if strategy.get("win_theme"):
        score += 20
    else:
        warnings.append("尚未形成明确赢标主张")
    if strategy.get("client_need"):
        score += 15
    else:
        warnings.append("客户核心诉求尚未明确")
    if strategy.get("differentiation"):
        score += min(20, len(strategy["differentiation"]) * 7)
    else:
        warnings.append("差异化优势尚未形成证据化表达")
    competitors = strategy.get("competitors") or []
    if competitors:
        score += min(15, len(competitors) * 6)
        if any(item.get("confidence", 0) < 60 for item in competitors):
            warnings.append("部分竞争对手判断置信度偏低")
    else:
        warnings.append("竞争对手画像为空")
    stakeholders = strategy.get("stakeholders") or []
    if stakeholders:
        score += min(15, len(stakeholders) * 5)
        if any(item.get("confidence", 0) < 60 for item in stakeholders):
            warnings.append("部分关键人关系判断缺乏证据")
    else:
        warnings.append("客户决策链尚未建立")
    if strategy.get("next_moves"):
        score += min(15, len(strategy["next_moves"]) * 5)
    else:
        warnings.append("缺少可执行的下一步经营动作")
    return min(100, score), warnings


def _label(score: int) -> str:
    if score >= 80:
        return "可进入重点攻坚"
    if score >= 60:
        return "策略基本成形"
    if score >= 40:
        return "需补关键情报"
    return "尚未形成策略"


def _strategy_version(opportunity_id: str, session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(OpportunityEventRecord)
            .where(
                OpportunityEventRecord.opportunity_id == opportunity_id,
                OpportunityEventRecord.event_type == "strategy_updated",
            )
        )
        or 0
    )


def get_strategy(opportunity_id: str, session: Session) -> StrategyWorkspace:
    opportunity = get_opportunity(opportunity_id, session)
    if not opportunity:
        raise ValueError("机会不存在")
    strategy = _default_strategy(opportunity)
    version = 0
    try:
        events = session.scalars(
            select(OpportunityEventRecord)
            .where(
                OpportunityEventRecord.opportunity_id == opportunity_id,
                OpportunityEventRecord.event_type == "strategy_updated",
            )
            .order_by(OpportunityEventRecord.occurred_at.desc(), OpportunityEventRecord.id.desc())
            .limit(1)
        ).all()
        if events:
            strategy.update(events[0].payload)
        version = _strategy_version(opportunity_id, session)
    except SQLAlchemyError:
        session.rollback()
    readiness, warnings = _readiness(strategy)
    return StrategyWorkspace(
        opportunity=opportunity.model_dump(),
        strategy=strategy,
        version=version,
        readiness=readiness,
        readiness_label=_label(readiness),
        evidence_warnings=warnings,
    )


def save_strategy(
    opportunity_id: str,
    payload: StrategyUpsert,
    session: Session,
    *,
    expected_version: int | None = None,
) -> StrategyWorkspace:
    # Every strategy writer locks the same opportunity row. This serializes competing
    # edits before checking the event-derived version and prevents lost updates.
    locked = session.scalar(
        select(OpportunityRecord)
        .where(OpportunityRecord.id == opportunity_id)
        .with_for_update()
    )
    if locked is None:
        raise ValueError("机会不存在")

    current_version = _strategy_version(opportunity_id, session)
    required_version = payload.expected_version if expected_version is None else expected_version
    if required_version != current_version:
        session.rollback()
        raise StrategyVersionConflict(required_version, current_version)

    data = payload.model_dump(exclude={"expected_version"})
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["version"] = current_version + 1
    session.add(
        OpportunityEventRecord(
            opportunity_id=opportunity_id,
            event_type="strategy_updated",
            payload=data,
        )
    )
    existing_titles = set(
        session.scalars(
            select(PursuitActionRecord.title).where(
                PursuitActionRecord.opportunity_id == opportunity_id,
                PursuitActionRecord.status == "open",
            )
        ).all()
    )
    for title in payload.next_moves:
        if title and title not in existing_titles:
            session.add(
                PursuitActionRecord(
                    opportunity_id=opportunity_id,
                    title=title,
                    owner="经营团队",
                    priority="high",
                    note="由赢标策略工作台同步",
                )
            )
    session.commit()
    return get_strategy(opportunity_id, session)

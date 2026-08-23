import re
from difflib import SequenceMatcher
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .ai import AIService
from .db import EvidenceRecord, OpportunityDraftRecord, OpportunityEventRecord, OpportunityRecord, ScoreSnapshotRecord, SourceRecord
from .models import ConfirmDraftRequest, ConfirmDraftResult, DiscoverRequest, DiscoverResult, DraftOpportunity, DuplicateMatch, ProjectDiscovery, ScoreBreakdown
from .repository import get_opportunity, list_opportunities
from .scoring import calculate_score
from .web_fetch import fetch_public_page


def _slug(text: str) -> str:
    asciiish = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (asciiish[:70] or "opportunity") + "-" + uuid4().hex[:8]


def _dedupe(discovery: ProjectDiscovery, session: Session) -> list[DuplicateMatch]:
    matches: list[DuplicateMatch] = []
    for item in list_opportunities(session):
        title_similarity = SequenceMatcher(None, discovery.title.lower(), item.title.lower()).ratio()
        country_bonus = 0.12 if discovery.country != "待识别" and discovery.country == item.country else 0
        score = min(1.0, title_similarity + country_bonus)
        if score >= 0.58:
            matches.append(DuplicateMatch(opportunity_id=item.id, title=item.title, country=item.country, similarity=round(score, 3)))
    return sorted(matches, key=lambda item: item.similarity, reverse=True)[:5]


async def discover(request: DiscoverRequest, session: Session) -> DiscoverResult:
    resolved_url = request.url
    page_title = request.source_title or "公开来源"
    text = request.text or ""
    if request.url:
        resolved_url, fetched_title, fetched_text = await fetch_public_page(request.url)
        text = fetched_text
        if fetched_title:
            page_title = fetched_title

    discovery, mode = await AIService().discover_project(text, page_title=page_title, use_ai=request.use_ai)
    duplicates = _dedupe(discovery, session) if discovery.project_detected else []
    draft_id = str(uuid4())
    persisted = False
    try:
        session.add(OpportunityDraftRecord(id=draft_id, status="pending", discovery=discovery.model_dump(), source_url=resolved_url, source_title=page_title, publisher=request.publisher, published_at=request.published_at, source_rank=request.source_rank, raw_text=text, duplicate_matches=[item.model_dump() for item in duplicates], is_demo=request.is_demo))
        session.commit()
        persisted = True
    except SQLAlchemyError:
        session.rollback()

    return DiscoverResult(
        mode=mode,
        draft=DraftOpportunity(id=draft_id, status="pending", discovery=discovery, source_url=resolved_url, source_title=page_title, publisher=request.publisher, published_at=request.published_at, source_rank=request.source_rank, duplicate_matches=duplicates, persisted=persisted),
        note=("已形成待确认商机草稿。系统不会自动写入正式机会池；请先检查字段与疑似重复项目。" if discovery.project_detected else "当前来源未形成足够明确的工程项目机会，建议补充原始公告或人工复核。"),
    )


def _initial_breakdown(discovery: ProjectDiscovery) -> ScoreBreakdown:
    values = {"strategic_fit": 0, "project_maturity": 0, "financing": 0, "client_quality": 0, "capability_fit": 0, "local_position": 0, "competition": 0, "risk_control": 0}
    limits = {"strategic_fit": 20, "project_maturity": 15, "financing": 15, "client_quality": 10, "capability_fit": 15, "local_position": 10, "competition": 10, "risk_control": 5}
    for fact in discovery.facts:
        if fact.score_hint is not None and fact.confidence >= 0.75:
            values[fact.field_name] = max(0, min(limits[fact.field_name], fact.score_hint))
    return ScoreBreakdown.model_validate(values)


def confirm_draft(draft_id: str, edits: ConfirmDraftRequest, session: Session) -> ConfirmDraftResult:
    draft = session.get(OpportunityDraftRecord, draft_id)
    if draft is None:
        raise ValueError("未找到可确认的商机草稿；请先初始化数据库并重新扫描。")
    if draft.status != "pending":
        raise ValueError("该草稿已处理，不能重复确认。")

    discovery = ProjectDiscovery.model_validate(draft.discovery)
    patch = edits.model_dump(exclude_none=True)
    if patch:
        discovery = discovery.model_copy(update=patch)
    if not discovery.project_detected:
        raise ValueError("当前草稿未识别出明确项目，不能直接入池。")

    opportunity_id = _slug(discovery.title)
    breakdown = _initial_breakdown(discovery)
    # A newly discovered opportunity normally has only one source. Force evidence-insufficient
    # status instead of treating unknown dimensions as proof that the opportunity is poor.
    confidence = max(20, min(44, round(discovery.confidence * 100)))
    score_result = calculate_score(breakdown, confidence)
    next_actions = ["补齐业主与决策链证据", "核实融资来源与采购时间表", "核实公司业绩与属地资源匹配度"]

    record = OpportunityRecord(id=opportunity_id, title=discovery.title, country=discovery.country, region=discovery.region, sector=discovery.sector, stage=discovery.stage, owner=discovery.owner, estimated_value_usd_m=discovery.estimated_value_usd_m, summary=discovery.summary, score=score_result.total, grade=score_result.grade, confidence=confidence, decision=score_result.decision, breakdown=breakdown.model_dump(), pursuit_thesis="该机会由公开来源自动发现并经人工确认入池；当前仅基于已有证据形成初始研判，需继续补齐经营情报。", next_actions=next_actions, is_demo=draft.is_demo)
    session.add(record)
    session.flush()

    source_id = str(uuid4())
    session.add(SourceRecord(id=source_id, opportunity_id=opportunity_id, title=draft.source_title, publisher=draft.publisher, published_at=draft.published_at, source_rank=draft.source_rank, url=draft.source_url, raw_text=draft.raw_text, is_demo=draft.is_demo))
    for fact in discovery.facts:
        session.add(EvidenceRecord(id=str(uuid4()), opportunity_id=opportunity_id, source_id=source_id, rank=draft.source_rank, title=draft.source_title, publisher=draft.publisher, published_at=draft.published_at, fact=fact.evidence_quote, field_name=fact.field_name, confidence=fact.confidence, source_url=draft.source_url))
    session.add(ScoreSnapshotRecord(opportunity_id=opportunity_id, total=score_result.total, grade=score_result.grade, breakdown=breakdown.model_dump(), note="公开来源发现并经人工确认入池后的初始评分；因证据不足暂不作 Go/No-Go 实质判断。"))
    session.add(OpportunityEventRecord(opportunity_id=opportunity_id, event_type="opportunity_confirmed_from_discovery", payload={"draft_id": draft.id, "source_id": source_id}))
    draft.status = "confirmed"
    session.commit()

    opportunity = get_opportunity(opportunity_id, session)
    if opportunity is None:
        raise RuntimeError("商机已创建但读取失败")
    return ConfirmDraftResult(opportunity=opportunity, source_bound=True, note="已人工确认入池。当前标记为证据不足，需继续补齐业主、融资、能力、属地和竞争等维度后再形成正式经营判断。")

import re
from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .ai import AIService
from .candidate_db import CandidateProcessingRecord
from .db import (
    EvidenceRecord,
    OpportunityDraftRecord,
    OpportunityEventRecord,
    OpportunityRecord,
    ScoreSnapshotRecord,
    SourceRecord,
)
from .document_store import DocumentStore, build_document_store
from .entity_management import enforce_reviewed_owner
from .intelligence import (
    aggregate_candidate_entities_to_opportunity,
    candidate_source_links,
)
from .intelligence_db import SourceDocumentInsightRecord
from .models import (
    ConfirmDraftRequest,
    ConfirmDraftResult,
    DiscoverRequest,
    DiscoverResult,
    DraftOpportunity,
    ProjectDiscovery,
    ScoreBreakdown,
)
from .project_matching import opportunity_duplicate_matches
from .repository import get_opportunity
from .scoring import calculate_score
from .source_db import SourceDocumentRecord
from .web_fetch import fetch_public_page


def _slug(text_value: str) -> str:
    asciiish = re.sub(r"[^a-zA-Z0-9]+", "-", text_value).strip("-").lower()
    return (asciiish[:70] or "opportunity") + "-" + uuid4().hex[:8]


async def discover(request: DiscoverRequest, session: Session) -> DiscoverResult:
    resolved_url = request.url
    page_title = request.source_title or "公开来源"
    text_value = request.text or ""
    if request.url:
        resolved_url, fetched_title, fetched_text = await fetch_public_page(request.url)
        text_value = fetched_text
        if fetched_title:
            page_title = fetched_title

    discovery, mode = await AIService().discover_project(
        text_value,
        page_title=page_title,
        use_ai=request.use_ai,
    )
    duplicates = opportunity_duplicate_matches(discovery, session) if discovery.project_detected else []
    draft_id = str(uuid4())
    persisted = False
    try:
        session.add(
            OpportunityDraftRecord(
                id=draft_id,
                status="pending",
                discovery=discovery.model_dump(),
                source_url=resolved_url,
                source_title=page_title,
                publisher=request.publisher,
                published_at=request.published_at,
                source_rank=request.source_rank,
                raw_text=text_value,
                duplicate_matches=[item.model_dump() for item in duplicates],
                is_demo=request.is_demo,
            )
        )
        session.commit()
        persisted = True
    except SQLAlchemyError:
        session.rollback()

    return DiscoverResult(
        mode=mode,
        draft=DraftOpportunity(
            id=draft_id,
            status="pending",
            discovery=discovery,
            source_url=resolved_url,
            source_title=page_title,
            publisher=request.publisher,
            published_at=request.published_at,
            source_rank=request.source_rank,
            duplicate_matches=duplicates,
            persisted=persisted,
        ),
        note=(
            "已形成待确认商机草稿。系统不会自动写入正式机会池；请先检查字段与疑似重复项目。"
            if discovery.project_detected
            else "当前来源未形成足够明确的工程项目机会，建议补充原始公告或人工复核。"
        ),
    )


def _initial_breakdown(discoveries: list[ProjectDiscovery]) -> ScoreBreakdown:
    values = {
        "strategic_fit": 0,
        "project_maturity": 0,
        "financing": 0,
        "client_quality": 0,
        "capability_fit": 0,
        "local_position": 0,
        "competition": 0,
        "risk_control": 0,
    }
    limits = {
        "strategic_fit": 20,
        "project_maturity": 15,
        "financing": 15,
        "client_quality": 10,
        "capability_fit": 15,
        "local_position": 10,
        "competition": 10,
        "risk_control": 5,
    }
    for discovery in discoveries:
        for fact in discovery.facts:
            if fact.score_hint is not None and fact.confidence >= 0.75:
                normalized = max(0, min(limits[fact.field_name], fact.score_hint))
                values[fact.field_name] = max(values[fact.field_name], normalized)
    return ScoreBreakdown.model_validate(values)


@dataclass(frozen=True)
class _CandidateEvidenceSource:
    source_document_id: str | None
    title: str
    publisher: str
    published_at: str
    source_rank: str
    url: str | None
    text: str
    discovery: ProjectDiscovery


def _read_document_text(document: SourceDocumentRecord, store: DocumentStore) -> str:
    raw = store.get(document.text_object_key)
    if sha256(raw).hexdigest() != document.content_sha256:
        raise RuntimeError("候选商机规范文本对象 SHA-256 校验失败")
    return raw.decode("utf-8", errors="strict")


def _candidate_evidence_sources(
    draft: OpportunityDraftRecord,
    primary_discovery: ProjectDiscovery,
    session: Session,
    *,
    store: DocumentStore | None = None,
) -> list[_CandidateEvidenceSource]:
    if draft.raw_text and draft.raw_text.strip():
        return [
            _CandidateEvidenceSource(
                source_document_id=None,
                title=draft.source_title,
                publisher=draft.publisher,
                published_at=draft.published_at,
                source_rank=draft.source_rank,
                url=draft.source_url,
                text=draft.raw_text,
                discovery=primary_discovery,
            )
        ]

    links = candidate_source_links(session, draft.id)
    # Backward-compatible fallback for an automatic Candidate created before 0012 is applied or
    # imported from an older database snapshot.
    if not links:
        processing = session.scalar(
            select(CandidateProcessingRecord).where(CandidateProcessingRecord.draft_id == draft.id)
        )
        if processing is None:
            raise ValueError("候选商机缺少原始 SourceDocument 关联，不能在无证据情况下入池。")
        from types import SimpleNamespace

        links = [
            SimpleNamespace(
                source_document_id=processing.source_document_id,
                is_primary=True,
            )
        ]

    resolved_store = store or build_document_store()
    result: list[_CandidateEvidenceSource] = []
    for link in links:
        document = session.get(SourceDocumentRecord, link.source_document_id)
        if document is None:
            raise ValueError("候选商机支持来源的 SourceDocument 已不存在，不能确认入池。")
        insight = session.get(SourceDocumentInsightRecord, document.id)
        source_discovery = primary_discovery
        if insight is not None:
            try:
                source_discovery = ProjectDiscovery.model_validate(insight.discovery)
            except (TypeError, ValueError):
                source_discovery = primary_discovery
        result.append(
            _CandidateEvidenceSource(
                source_document_id=document.id,
                title=document.title,
                publisher=document.publisher or "公开来源",
                published_at=(
                    document.published_at.isoformat() if document.published_at else "待核实"
                ),
                source_rank=draft.source_rank,
                url=document.canonical_url,
                text=_read_document_text(document, resolved_store),
                discovery=source_discovery,
            )
        )
    if not result:
        raise ValueError("候选商机没有可验证的支持来源，不能确认入池。")
    return result


def confirm_draft(
    draft_id: str,
    edits: ConfirmDraftRequest,
    session: Session,
    *,
    store: DocumentStore | None = None,
) -> ConfirmDraftResult:
    draft = session.get(OpportunityDraftRecord, draft_id)
    if draft is None:
        raise ValueError("未找到可确认的商机草稿；请先初始化数据库并重新扫描。")
    if draft.status != "pending":
        raise ValueError("该草稿已处理，不能重复确认。")

    primary_discovery = ProjectDiscovery.model_validate(draft.discovery)
    patch = edits.model_dump(exclude_none=True)
    reviewed_discovery = (
        primary_discovery.model_copy(update=patch) if patch else primary_discovery
    )
    if not reviewed_discovery.project_detected:
        raise ValueError("当前草稿未识别出明确项目，不能直接入池。")

    evidence_sources = _candidate_evidence_sources(
        draft,
        reviewed_discovery,
        session,
        store=store,
    )
    discoveries = [item.discovery for item in evidence_sources]
    # Human-reviewed headline fields remain authoritative, while facts from every supporting
    # source contribute to the initial breakdown.
    if reviewed_discovery not in discoveries:
        discoveries.insert(0, reviewed_discovery)

    opportunity_id = _slug(reviewed_discovery.title)
    breakdown = _initial_breakdown(discoveries)
    # Even multiple public B-rank sources are not enough by themselves to unlock a substantive
    # Go/No-Go decision. Confidence remains below 45 until later verified evidence arrives.
    confidence = max(20, min(44, round(reviewed_discovery.confidence * 100)))
    score_result = calculate_score(breakdown, confidence)
    next_actions = [
        "补齐业主与决策链证据",
        "核实融资来源与采购时间表",
        "核实公司业绩与属地资源匹配度",
    ]

    record = OpportunityRecord(
        id=opportunity_id,
        title=reviewed_discovery.title,
        country=reviewed_discovery.country,
        region=reviewed_discovery.region,
        sector=reviewed_discovery.sector,
        stage=reviewed_discovery.stage,
        owner=reviewed_discovery.owner,
        estimated_value_usd_m=reviewed_discovery.estimated_value_usd_m,
        summary=reviewed_discovery.summary,
        score=score_result.total,
        grade=score_result.grade,
        confidence=confidence,
        decision=score_result.decision,
        breakdown=breakdown.model_dump(),
        pursuit_thesis=(
            "该机会由公开来源自动发现并经人工确认入池；当前仅基于已有证据形成初始研判，"
            "需继续补齐经营情报。"
        ),
        next_actions=next_actions,
        is_demo=draft.is_demo,
    )
    session.add(record)
    session.flush()

    source_ids: list[str] = []
    source_document_ids: list[str] = []
    for evidence_source in evidence_sources:
        source_id = str(uuid4())
        source_ids.append(source_id)
        if evidence_source.source_document_id:
            source_document_ids.append(evidence_source.source_document_id)
        session.add(
            SourceRecord(
                id=source_id,
                opportunity_id=opportunity_id,
                title=evidence_source.title,
                publisher=evidence_source.publisher,
                published_at=evidence_source.published_at,
                source_rank=evidence_source.source_rank,
                url=evidence_source.url,
                raw_text=evidence_source.text,
                is_demo=draft.is_demo,
            )
        )
        session.flush()
        # Production PostgreSQL has an explicit source_document_id provenance column from 0012.
        # SQLite unit tests build metadata directly and intentionally omit migration-only columns.
        if evidence_source.source_document_id and session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("UPDATE sources SET source_document_id=:document WHERE id=:source"),
                {"document": evidence_source.source_document_id, "source": source_id},
            )
        for fact in evidence_source.discovery.facts:
            session.add(
                EvidenceRecord(
                    id=str(uuid4()),
                    opportunity_id=opportunity_id,
                    source_id=source_id,
                    rank=evidence_source.source_rank,
                    title=evidence_source.title,
                    publisher=evidence_source.publisher,
                    published_at=evidence_source.published_at,
                    fact=fact.evidence_quote,
                    field_name=fact.field_name,
                    confidence=fact.confidence,
                    source_url=evidence_source.url,
                )
            )

    entity_links = aggregate_candidate_entities_to_opportunity(
        session,
        draft_id=draft.id,
        opportunity_id=opportunity_id,
        fallback_discovery=reviewed_discovery,
    )
    reviewed_owner_link = enforce_reviewed_owner(
        session,
        opportunity_id=opportunity_id,
        discovery=reviewed_discovery,
        source_count=len(evidence_sources),
    )
    if reviewed_owner_link is not None and all(
        item.id != reviewed_owner_link.id for item in entity_links if item.id is not None
    ):
        entity_links.append(reviewed_owner_link)

    session.add(
        ScoreSnapshotRecord(
            opportunity_id=opportunity_id,
            total=score_result.total,
            grade=score_result.grade,
            breakdown=breakdown.model_dump(),
            note=(
                f"公开来源发现并经人工确认入池后的初始评分；已汇聚 {len(evidence_sources)} 份支持来源，"
                "因证据等级仍不足暂不作 Go/No-Go 实质判断。"
            ),
        )
    )
    session.add(
        OpportunityEventRecord(
            opportunity_id=opportunity_id,
            event_type="opportunity_confirmed_from_discovery",
            payload={
                "draft_id": draft.id,
                "source_ids": source_ids,
                "source_document_ids": source_document_ids,
                "source_count": len(evidence_sources),
                "entity_link_count": len(entity_links),
            },
        )
    )
    draft.status = "confirmed"
    session.commit()

    opportunity = get_opportunity(opportunity_id, session)
    if opportunity is None:
        raise RuntimeError("商机已创建但读取失败")
    return ConfirmDraftResult(
        opportunity=opportunity,
        source_bound=True,
        note=(
            f"已人工确认入池，并汇聚 {len(evidence_sources)} 份来源。当前仍标记为证据不足，需继续补齐"
            "业主、融资、能力、属地和竞争等维度后再形成正式经营判断。"
        ),
    )

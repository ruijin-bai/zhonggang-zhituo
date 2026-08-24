from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .candidate_db import CandidateProcessingRecord
from .db import (
    EvidenceRecord,
    OpportunityDraftRecord,
    OpportunityEventRecord,
    OpportunityRecord,
    SourceRecord,
    utc_now,
)
from .document_store import DocumentStore, build_document_store
from .intelligence import candidate_source_links, resolve_discovery_entities
from .intelligence_db import (
    OpportunityEntityLinkRecord,
    SourceDocumentInsightRecord,
    SourceEntityMentionRecord,
)
from .models import ProjectDiscovery, ProjectParty
from .opportunity_evidence_db import OpportunitySourceDocumentRecord
from .source_db import SourceDocumentRecord

_UNKNOWN_VALUES = {"", "待识别", "待核实", "unknown", "n/a", "na", "none", "-"}


def _known(value: str | None) -> bool:
    return bool(value and value.strip().casefold() not in _UNKNOWN_VALUES)


def _read_document_text(document: SourceDocumentRecord, store: DocumentStore) -> str:
    raw = store.get(document.text_object_key)
    if sha256(raw).hexdigest() != document.content_sha256:
        raise RuntimeError("正式机会补充来源的规范文本对象 SHA-256 校验失败")
    return raw.decode("utf-8", errors="strict")


def link_opportunity_source_document(
    session: Session,
    *,
    opportunity_id: str,
    source_document_id: str,
    source_id: str | None,
) -> OpportunitySourceDocumentRecord:
    existing = session.scalar(
        select(OpportunitySourceDocumentRecord).where(
            OpportunitySourceDocumentRecord.source_document_id == source_document_id
        )
    )
    if existing is not None:
        if existing.opportunity_id != opportunity_id:
            raise ValueError(
                "该 SourceDocument 已绑定到其他正式 Opportunity；当前单项目识别模型禁止一份规范文档自动跨项目复用。"
            )
        if source_id and existing.source_id is None:
            existing.source_id = source_id
            session.flush()
        return existing

    row = OpportunitySourceDocumentRecord(
        opportunity_id=opportunity_id,
        source_document_id=source_document_id,
        source_id=source_id,
        linked_at=utc_now(),
    )
    session.add(row)
    session.flush()
    return row


def _reviewed_owner_entity_id(
    session: Session,
    opportunity: OpportunityRecord,
) -> str | None:
    if not _known(opportunity.owner):
        return None
    discovery = ProjectDiscovery(
        project_detected=True,
        title=opportunity.title,
        country=opportunity.country,
        region=opportunity.region,
        sector=opportunity.sector,
        stage=opportunity.stage,
        owner=opportunity.owner,
        estimated_value_usd_m=opportunity.estimated_value_usd_m,
        summary=opportunity.summary,
        confidence=1.0,
        facts=[],
        parties=[
            ProjectParty(
                role="owner",
                name=opportunity.owner,
                country=opportunity.country if _known(opportunity.country) else None,
                evidence_quote="",
                confidence=1.0,
            )
        ],
    )
    resolved = resolve_discovery_entities(
        session,
        discovery=discovery,
        source_document_id=None,
    )
    owner = next((item for item in resolved if item["role"] == "owner"), None)
    return owner["entity_id"] if owner else None


def sync_opportunity_entities(
    session: Session,
    *,
    opportunity_id: str,
) -> list[OpportunityEntityLinkRecord]:
    opportunity = session.get(OpportunityRecord, opportunity_id)
    if opportunity is None:
        raise ValueError("未找到目标正式 Opportunity")

    document_ids = list(
        session.scalars(
            select(OpportunitySourceDocumentRecord.source_document_id).where(
                OpportunitySourceDocumentRecord.opportunity_id == opportunity_id
            )
        ).all()
    )
    mentions = []
    if document_ids:
        mentions = session.scalars(
            select(SourceEntityMentionRecord).where(
                SourceEntityMentionRecord.source_document_id.in_(document_ids)
            )
        ).all()

    grouped: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"confidence": 0.0, "source_ids": set()}
    )
    for mention in mentions:
        key = (mention.entity_id, mention.role)
        grouped[key]["confidence"] = max(grouped[key]["confidence"], mention.confidence)
        grouped[key]["source_ids"].add(mention.source_document_id)

    # The human-reviewed Opportunity.owner is authoritative for the formal owner relationship.
    # Source mentions remain untouched as provenance, but conflicting machine owner links are not
    # promoted into the formal Opportunity relationship layer.
    reviewed_owner_id = _reviewed_owner_entity_id(session, opportunity)
    if reviewed_owner_id:
        owner_source_ids = {
            mention.source_document_id
            for mention in mentions
            if mention.role == "owner" and mention.entity_id == reviewed_owner_id
        }
        for key in [item for item in grouped if item[1] == "owner"]:
            grouped.pop(key, None)
        grouped[(reviewed_owner_id, "owner")] = {
            "confidence": 1.0,
            "source_ids": owner_source_ids,
        }
        session.execute(
            delete(OpportunityEntityLinkRecord).where(
                OpportunityEntityLinkRecord.opportunity_id == opportunity_id,
                OpportunityEntityLinkRecord.role == "owner",
                OpportunityEntityLinkRecord.entity_id != reviewed_owner_id,
            )
        )

    now = utc_now()
    result: list[OpportunityEntityLinkRecord] = []
    for (entity_id, role), data in grouped.items():
        source_count = len(data["source_ids"])
        existing = session.scalar(
            select(OpportunityEntityLinkRecord).where(
                OpportunityEntityLinkRecord.opportunity_id == opportunity_id,
                OpportunityEntityLinkRecord.entity_id == entity_id,
                OpportunityEntityLinkRecord.role == role,
            )
        )
        if existing is None:
            existing = OpportunityEntityLinkRecord(
                opportunity_id=opportunity_id,
                entity_id=entity_id,
                role=role,
                confidence=float(data["confidence"]),
                source_count=source_count,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(existing)
        else:
            existing.confidence = max(existing.confidence, float(data["confidence"]))
            existing.source_count = source_count
            existing.last_seen_at = now
        result.append(existing)
    session.flush()
    return result


def attach_candidate_to_opportunity(
    session: Session,
    *,
    draft_id: str,
    opportunity_id: str,
    store: DocumentStore | None = None,
) -> dict:
    draft = session.get(OpportunityDraftRecord, draft_id)
    if draft is None:
        raise ValueError("未找到候选商机")
    if draft.status != "pending":
        raise ValueError("该候选商机已处理，不能再次挂接为补充证据")
    opportunity = session.get(OpportunityRecord, opportunity_id)
    if opportunity is None:
        raise ValueError("未找到目标正式 Opportunity")

    links = candidate_source_links(session, draft_id)
    if not links:
        processing = session.scalar(
            select(CandidateProcessingRecord).where(CandidateProcessingRecord.draft_id == draft_id)
        )
        if processing is None:
            raise ValueError("候选商机没有可验证的 SourceDocument，不能挂接为正式证据")
        source_document_ids = [processing.source_document_id]
    else:
        source_document_ids = [item.source_document_id for item in links]

    resolved_store = store or build_document_store()
    attached = 0
    source_ids: list[str] = []
    for source_document_id in source_document_ids:
        prior = session.scalar(
            select(OpportunitySourceDocumentRecord).where(
                OpportunitySourceDocumentRecord.source_document_id == source_document_id
            )
        )
        if prior is not None:
            if prior.opportunity_id != opportunity_id:
                raise ValueError(
                    "候选来源中存在已绑定其他正式 Opportunity 的文档，拒绝跨项目复用。"
                )
            continue

        document = session.get(SourceDocumentRecord, source_document_id)
        insight = session.get(SourceDocumentInsightRecord, source_document_id)
        if document is None or insight is None:
            raise ValueError("候选来源缺少 SourceDocument 或结构化 Insight，不能挂接")
        discovery = ProjectDiscovery.model_validate(insight.discovery)
        if not discovery.project_detected:
            raise ValueError("候选来源未识别出明确项目，不能作为正式 Opportunity 的项目证据")

        # Re-resolve defensively in case the document insight came from a legacy backfill before
        # entity mentions were introduced.
        resolve_discovery_entities(
            session,
            discovery=discovery,
            source_document_id=source_document_id,
        )
        source_id = str(uuid4())
        source_ids.append(source_id)
        session.add(
            SourceRecord(
                id=source_id,
                opportunity_id=opportunity_id,
                title=document.title,
                publisher=document.publisher or draft.publisher or "公开来源",
                published_at=(document.published_at.isoformat() if document.published_at else draft.published_at),
                source_rank=draft.source_rank,
                url=document.canonical_url,
                raw_text=_read_document_text(document, resolved_store),
                is_demo=draft.is_demo,
            )
        )
        session.flush()
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("UPDATE sources SET source_document_id=:document WHERE id=:source"),
                {"document": source_document_id, "source": source_id},
            )
        link_opportunity_source_document(
            session,
            opportunity_id=opportunity_id,
            source_document_id=source_document_id,
            source_id=source_id,
        )
        for fact in discovery.facts:
            session.add(
                EvidenceRecord(
                    id=str(uuid4()),
                    opportunity_id=opportunity_id,
                    source_id=source_id,
                    rank=draft.source_rank,
                    title=document.title,
                    publisher=document.publisher or draft.publisher or "公开来源",
                    published_at=(document.published_at.isoformat() if document.published_at else draft.published_at),
                    fact=fact.evidence_quote,
                    field_name=fact.field_name,
                    confidence=fact.confidence,
                    source_url=document.canonical_url,
                )
            )
        attached += 1

    entity_links = sync_opportunity_entities(session, opportunity_id=opportunity_id)
    draft.status = "linked"
    draft.updated_at = utc_now()
    session.add(
        OpportunityEventRecord(
            opportunity_id=opportunity_id,
            event_type="candidate_attached_as_evidence",
            payload={
                "draft_id": draft_id,
                "source_document_ids": source_document_ids,
                "source_ids": source_ids,
                "attached_count": attached,
                "entity_link_count": len(entity_links),
            },
        )
    )
    session.flush()
    return {
        "draft_id": draft_id,
        "opportunity_id": opportunity_id,
        "status": "linked",
        "attached_count": attached,
        "source_document_count": len(source_document_ids),
        "entity_link_count": len(entity_links),
    }

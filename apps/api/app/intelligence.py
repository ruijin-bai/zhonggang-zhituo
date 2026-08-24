from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import utc_now
from .intelligence_db import (
    CandidateSourceDocumentRecord,
    EntityAliasRecord,
    EntityRecord,
    OpportunityEntityLinkRecord,
    SourceDocumentInsightRecord,
    SourceEntityMentionRecord,
)
from .models import ProjectDiscovery, ProjectParty
from .source_db import SourceDocumentRecord

_UNKNOWN_VALUES = {"", "待识别", "待核实", "unknown", "n/a", "na", "none", "-"}


def normalize_entity_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold().strip()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _known(value: str | None) -> bool:
    return bool(value and value.strip().casefold() not in _UNKNOWN_VALUES)


def _country_key(value: str | None) -> str:
    return normalize_entity_name(value or "") if _known(value) else ""


def _identity_key(name: str, country_key: str) -> str:
    return sha256(f"organization|{name}|{country_key}".encode("utf-8")).hexdigest()


def project_identity_fingerprint(discovery: ProjectDiscovery) -> str | None:
    if not discovery.project_detected:
        return None
    fields = (
        normalize_entity_name(discovery.title),
        _country_key(discovery.country),
        normalize_entity_name(discovery.sector),
        normalize_entity_name(discovery.owner),
    )
    return sha256("|".join(fields).encode("utf-8")).hexdigest()


def record_document_insight(
    session: Session,
    *,
    source_document_id: str,
    discovery: ProjectDiscovery,
    extraction_mode: str,
) -> SourceDocumentInsightRecord:
    now = utc_now()
    row = session.get(SourceDocumentInsightRecord, source_document_id)
    if row is None:
        row = SourceDocumentInsightRecord(
            id=source_document_id,
            source_document_id=source_document_id,
            project_detected=discovery.project_detected,
            extraction_mode=extraction_mode,
            discovery=discovery.model_dump(mode="json"),
            identity_fingerprint=project_identity_fingerprint(discovery),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.project_detected = discovery.project_detected
        row.extraction_mode = extraction_mode
        row.discovery = discovery.model_dump(mode="json")
        row.identity_fingerprint = project_identity_fingerprint(discovery)
        row.updated_at = now
    session.flush()
    return row


def link_candidate_source(
    session: Session,
    *,
    draft_id: str,
    source_document_id: str,
    is_primary: bool,
) -> CandidateSourceDocumentRecord:
    existing = session.scalar(
        select(CandidateSourceDocumentRecord).where(
            CandidateSourceDocumentRecord.draft_id == draft_id,
            CandidateSourceDocumentRecord.source_document_id == source_document_id,
        )
    )
    if existing is not None:
        if is_primary and not existing.is_primary:
            existing.is_primary = True
            session.flush()
        return existing
    row = CandidateSourceDocumentRecord(
        draft_id=draft_id,
        source_document_id=source_document_id,
        is_primary=is_primary,
        added_at=utc_now(),
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
        return row
    except IntegrityError:
        existing = session.scalar(
            select(CandidateSourceDocumentRecord).where(
                CandidateSourceDocumentRecord.draft_id == draft_id,
                CandidateSourceDocumentRecord.source_document_id == source_document_id,
            )
        )
        if existing is None:
            raise
        return existing


def candidate_source_links(session: Session, draft_id: str) -> list[CandidateSourceDocumentRecord]:
    return session.scalars(
        select(CandidateSourceDocumentRecord)
        .where(CandidateSourceDocumentRecord.draft_id == draft_id)
        .order_by(CandidateSourceDocumentRecord.is_primary.desc(), CandidateSourceDocumentRecord.added_at.asc())
    ).all()


def candidate_source_documents(session: Session, draft_id: str) -> list[SourceDocumentRecord]:
    links = candidate_source_links(session, draft_id)
    if not links:
        return []
    by_id = {
        row.id: row
        for row in session.scalars(
            select(SourceDocumentRecord).where(
                SourceDocumentRecord.id.in_([item.source_document_id for item in links])
            )
        ).all()
    }
    return [by_id[item.source_document_id] for item in links if item.source_document_id in by_id]


def candidate_discoveries(session: Session, draft_id: str) -> list[ProjectDiscovery]:
    links = candidate_source_links(session, draft_id)
    if not links:
        return []
    insights = session.scalars(
        select(SourceDocumentInsightRecord).where(
            SourceDocumentInsightRecord.source_document_id.in_(
                [item.source_document_id for item in links]
            )
        )
    ).all()
    by_id = {item.source_document_id: item for item in insights}
    result: list[ProjectDiscovery] = []
    for link in links:
        insight = by_id.get(link.source_document_id)
        if insight is None:
            continue
        try:
            result.append(ProjectDiscovery.model_validate(insight.discovery))
        except (TypeError, ValueError):
            continue
    return result


def _effective_parties(discovery: ProjectDiscovery) -> list[ProjectParty]:
    parties = list(discovery.parties)
    has_owner = any(item.role == "owner" for item in parties)
    if not has_owner and _known(discovery.owner):
        parties.append(
            ProjectParty(
                role="owner",
                name=discovery.owner,
                country=discovery.country if _known(discovery.country) else None,
                evidence_quote="",
                confidence=min(1.0, max(0.5, discovery.confidence)),
            )
        )
    return parties


def _resolve_entity(
    session: Session,
    *,
    party: ProjectParty,
    project_country: str,
    source_document_id: str | None,
) -> tuple[EntityRecord, str]:
    normalized = normalize_entity_name(party.name)
    if not normalized or normalized in _UNKNOWN_VALUES:
        raise ValueError("party name is not a resolvable entity")
    resolved_country = party.country if _known(party.country) else (
        project_country if _known(project_country) else None
    )
    country_key = _country_key(resolved_country)

    # Automatic resolution is intentionally conservative: exact normalized alias and compatible
    # country only. Fuzzy name similarity is a suggestion problem, not an automatic merge rule.
    aliases = session.scalars(
        select(EntityAliasRecord)
        .join(EntityRecord, EntityRecord.id == EntityAliasRecord.entity_id)
        .where(
            EntityAliasRecord.normalized_alias == normalized,
            EntityRecord.entity_type == "organization",
            EntityRecord.status == "active",
        )
    ).all()
    exact_entity: EntityRecord | None = None
    for alias in aliases:
        entity = session.get(EntityRecord, alias.entity_id)
        if entity is None:
            continue
        if entity.country_key == country_key:
            exact_entity = entity
            break
    if exact_entity is not None:
        return exact_entity, "exact_alias"

    identity_key = _identity_key(normalized, country_key)
    existing = session.scalar(
        select(EntityRecord).where(
            EntityRecord.entity_type == "organization",
            EntityRecord.identity_key == identity_key,
        )
    )
    if existing is not None:
        return existing, "exact_identity"

    entity = EntityRecord(
        id=str(uuid4()),
        entity_type="organization",
        canonical_name=party.name.strip(),
        normalized_name=normalized,
        country=resolved_country,
        country_key=country_key,
        identity_key=identity_key,
        status="active",
        entity_metadata={},
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    try:
        with session.begin_nested():
            session.add(entity)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(EntityRecord).where(
                EntityRecord.entity_type == "organization",
                EntityRecord.identity_key == identity_key,
            )
        )
        if existing is None:
            raise
        entity = existing

    alias = EntityAliasRecord(
        entity_id=entity.id,
        alias=party.name.strip(),
        normalized_alias=normalized,
        source_document_id=source_document_id,
        confidence=party.confidence,
        created_at=utc_now(),
    )
    try:
        with session.begin_nested():
            session.add(alias)
            session.flush()
    except IntegrityError:
        pass
    return entity, "created"


def resolve_discovery_entities(
    session: Session,
    *,
    discovery: ProjectDiscovery,
    source_document_id: str | None,
) -> list[dict]:
    resolved: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for party in _effective_parties(discovery):
        normalized = normalize_entity_name(party.name)
        key = (party.role, normalized)
        if key in seen or not normalized:
            continue
        seen.add(key)
        try:
            entity, resolver = _resolve_entity(
                session,
                party=party,
                project_country=discovery.country,
                source_document_id=source_document_id,
            )
        except ValueError:
            continue
        if source_document_id:
            mention = SourceEntityMentionRecord(
                source_document_id=source_document_id,
                entity_id=entity.id,
                role=party.role,
                name_text=party.name.strip(),
                evidence_quote=party.evidence_quote.strip(),
                confidence=party.confidence,
                resolver=resolver,
                created_at=utc_now(),
            )
            try:
                with session.begin_nested():
                    session.add(mention)
                    session.flush()
            except IntegrityError:
                existing = session.scalar(
                    select(SourceEntityMentionRecord).where(
                        SourceEntityMentionRecord.source_document_id == source_document_id,
                        SourceEntityMentionRecord.entity_id == entity.id,
                        SourceEntityMentionRecord.role == party.role,
                    )
                )
                if existing is not None and party.confidence > existing.confidence:
                    existing.confidence = party.confidence
                    if party.evidence_quote:
                        existing.evidence_quote = party.evidence_quote.strip()
        resolved.append(
            {
                "entity_id": entity.id,
                "canonical_name": entity.canonical_name,
                "country": entity.country,
                "role": party.role,
                "confidence": party.confidence,
                "resolver": resolver,
            }
        )
    return resolved


def aggregate_candidate_entities_to_opportunity(
    session: Session,
    *,
    draft_id: str,
    opportunity_id: str,
    fallback_discovery: ProjectDiscovery,
) -> list[OpportunityEntityLinkRecord]:
    links = candidate_source_links(session, draft_id)
    source_document_ids = [item.source_document_id for item in links]
    mentions = []
    if source_document_ids:
        mentions = session.scalars(
            select(SourceEntityMentionRecord).where(
                SourceEntityMentionRecord.source_document_id.in_(source_document_ids)
            )
        ).all()

    # Manual discovery drafts have no SourceDocument. Resolve their explicit structured parties
    # directly so confirmed opportunities still get a usable entity layer.
    if not mentions:
        resolved = resolve_discovery_entities(
            session,
            discovery=fallback_discovery,
            source_document_id=None,
        )
        grouped = {
            (item["entity_id"], item["role"]): {
                "confidence": item["confidence"],
                "source_count": 1,
            }
            for item in resolved
        }
    else:
        grouped_map: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"confidence": 0.0, "source_ids": set()}
        )
        for mention in mentions:
            key = (mention.entity_id, mention.role)
            grouped_map[key]["confidence"] = max(
                grouped_map[key]["confidence"], mention.confidence
            )
            grouped_map[key]["source_ids"].add(mention.source_document_id)
        grouped = {
            key: {
                "confidence": value["confidence"],
                "source_count": len(value["source_ids"]),
            }
            for key, value in grouped_map.items()
        }

    now = utc_now()
    result: list[OpportunityEntityLinkRecord] = []
    for (entity_id, role), data in grouped.items():
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
                source_count=int(data["source_count"]),
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(existing)
        else:
            existing.confidence = max(existing.confidence, float(data["confidence"]))
            existing.source_count = max(existing.source_count, int(data["source_count"]))
            existing.last_seen_at = now
        result.append(existing)
    session.flush()
    return result


def candidate_intelligence_summary(session: Session, draft_id: str) -> dict:
    links = candidate_source_links(session, draft_id)
    source_ids = [item.source_document_id for item in links]
    entities: list[dict] = []
    if source_ids:
        mentions = session.scalars(
            select(SourceEntityMentionRecord).where(
                SourceEntityMentionRecord.source_document_id.in_(source_ids)
            )
        ).all()
        seen: set[tuple[str, str]] = set()
        for mention in mentions:
            key = (mention.entity_id, mention.role)
            if key in seen:
                continue
            seen.add(key)
            entity = session.get(EntityRecord, mention.entity_id)
            if entity is None:
                continue
            supporting = sum(
                1
                for item in mentions
                if item.entity_id == mention.entity_id and item.role == mention.role
            )
            entities.append(
                {
                    "id": entity.id,
                    "name": entity.canonical_name,
                    "country": entity.country,
                    "role": mention.role,
                    "source_count": supporting,
                }
            )
    return {
        "source_count": len(links),
        "source_document_ids": source_ids,
        "entities": entities,
    }


def list_entities(session: Session, *, limit: int = 200, query: str | None = None) -> list[dict]:
    statement = select(EntityRecord).where(EntityRecord.status == "active")
    if query and query.strip():
        normalized = normalize_entity_name(query)
        statement = statement.where(EntityRecord.normalized_name.contains(normalized))
    rows = session.scalars(
        statement.order_by(EntityRecord.updated_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": item.id,
            "entity_type": item.entity_type,
            "canonical_name": item.canonical_name,
            "country": item.country,
            "status": item.status,
            "opportunity_count": session.scalar(
                select(func.count(func.distinct(OpportunityEntityLinkRecord.opportunity_id))).where(
                    OpportunityEntityLinkRecord.entity_id == item.id
                )
            )
            or 0,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }
        for item in rows
    ]


def entity_detail(session: Session, entity_id: str) -> dict | None:
    entity = session.get(EntityRecord, entity_id)
    if entity is None:
        return None
    aliases = session.scalars(
        select(EntityAliasRecord)
        .where(EntityAliasRecord.entity_id == entity_id)
        .order_by(EntityAliasRecord.created_at.asc())
    ).all()
    opportunity_links = session.scalars(
        select(OpportunityEntityLinkRecord)
        .where(OpportunityEntityLinkRecord.entity_id == entity_id)
        .order_by(OpportunityEntityLinkRecord.last_seen_at.desc())
    ).all()
    return {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "canonical_name": entity.canonical_name,
        "country": entity.country,
        "status": entity.status,
        "aliases": [
            {
                "alias": item.alias,
                "confidence": item.confidence,
                "source_document_id": item.source_document_id,
            }
            for item in aliases
        ],
        "opportunities": [
            {
                "opportunity_id": item.opportunity_id,
                "role": item.role,
                "confidence": item.confidence,
                "source_count": item.source_count,
                "last_seen_at": item.last_seen_at.isoformat(),
            }
            for item in opportunity_links
        ],
        "metadata": entity.entity_metadata or {},
        "created_at": entity.created_at.isoformat(),
        "updated_at": entity.updated_at.isoformat(),
    }

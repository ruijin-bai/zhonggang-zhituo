from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .db import (
    EvidenceRecord,
    OpportunityDraftRecord,
    OpportunityEventRecord,
    OpportunityRecord,
    SourceRecord,
)
from .intelligence_db import (
    EntityAliasRecord,
    EntityRecord,
    OpportunityEntityLinkRecord,
)
from .models import ProjectDiscovery
from .opportunity_evidence_db import OpportunitySourceDocumentRecord

SEARCH_TYPES = {"opportunity", "candidate", "entity", "evidence", "source"}


def _normalize(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _tokens(query: str) -> list[str]:
    return [item for item in re.split(r"\s+", _normalize(query)) if item]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_clauses(columns: Iterable, query: str):
    terms = _tokens(query)
    if not terms:
        return []
    clauses = []
    for term in terms:
        pattern = f"%{_escape_like(term)}%"
        for column in columns:
            clauses.append(column.ilike(pattern, escape="\\"))
    return clauses


def _rank(query: str, fields: list[tuple[str, str | None, int]]) -> tuple[int, list[str]]:
    q = _normalize(query)
    terms = _tokens(query)
    raw = 0
    matched: list[str] = []
    for name, value, weight in fields:
        normalized = _normalize(value)
        if not normalized:
            continue
        field_score = 0
        if normalized == q:
            field_score = 32 * weight
        elif normalized.startswith(q):
            field_score = 24 * weight
        elif q and q in normalized:
            field_score = 18 * weight
        else:
            hit_count = sum(1 for term in terms if term in normalized)
            if hit_count:
                field_score = (7 * hit_count + (6 if hit_count == len(terms) else 0)) * weight
        if field_score:
            raw += field_score
            matched.append(name)
    # This is deterministic retrieval relevance only, not a probability or business score.
    return min(100, raw), list(dict.fromkeys(matched))


def _snippet(value: str | None, query: str, *, width: int = 260) -> str:
    text = " ".join((value or "").split())
    if len(text) <= width:
        return text
    lowered = text.casefold()
    positions = [lowered.find(term) for term in _tokens(query)]
    positions = [item for item in positions if item >= 0]
    start = max(0, (min(positions) if positions else 0) - width // 4)
    end = min(len(text), start + width)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _result(
    *,
    resource_type: str,
    resource_id: str,
    title: str,
    subtitle: str,
    snippet: str,
    relevance_score: int,
    matched_fields: list[str],
    opportunity_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "title": title,
        "subtitle": subtitle,
        "snippet": snippet,
        "relevance_score": relevance_score,
        "matched_fields": matched_fields,
        "opportunity_id": opportunity_id,
        "metadata": metadata or {},
    }


def search_knowledge(
    session: Session,
    *,
    query: str,
    resource_types: set[str] | None = None,
    country: str | None = None,
    sector: str | None = None,
    entity_role: str | None = None,
    source_rank: str | None = None,
    limit: int = 30,
) -> dict:
    requested = resource_types or SEARCH_TYPES
    unknown = requested - SEARCH_TYPES
    if unknown:
        raise ValueError(f"unsupported search resource types: {', '.join(sorted(unknown))}")

    results: list[dict] = []
    candidate_cap = min(max(limit * 8, 80), 800)

    if "opportunity" in requested:
        clauses = _like_clauses(
            (
                OpportunityRecord.title,
                OpportunityRecord.summary,
                OpportunityRecord.owner,
                OpportunityRecord.country,
                OpportunityRecord.region,
                OpportunityRecord.sector,
                OpportunityRecord.stage,
            ),
            query,
        )
        statement = select(OpportunityRecord)
        if clauses:
            statement = statement.where(or_(*clauses))
        if country:
            statement = statement.where(OpportunityRecord.country.ilike(country))
        if sector:
            statement = statement.where(OpportunityRecord.sector.ilike(sector))
        if entity_role:
            statement = statement.where(
                OpportunityRecord.id.in_(
                    select(OpportunityEntityLinkRecord.opportunity_id).where(
                        OpportunityEntityLinkRecord.role == entity_role
                    )
                )
            )
        rows = session.scalars(statement.limit(candidate_cap)).all()
        for row in rows:
            score, matched = _rank(
                query,
                [
                    ("title", row.title, 5),
                    ("owner", row.owner, 4),
                    ("country", row.country, 2),
                    ("region", row.region, 1),
                    ("sector", row.sector, 3),
                    ("stage", row.stage, 2),
                    ("summary", row.summary, 2),
                ],
            )
            if not score:
                continue
            results.append(
                _result(
                    resource_type="opportunity",
                    resource_id=row.id,
                    title=row.title,
                    subtitle=f"{row.country} · {row.sector} · {row.stage}",
                    snippet=_snippet(row.summary, query),
                    relevance_score=score,
                    matched_fields=matched,
                    opportunity_id=row.id,
                    metadata={
                        "owner": row.owner,
                        "score": row.score,
                        "grade": row.grade,
                        "decision": row.decision,
                        "confidence": row.confidence,
                    },
                )
            )

    if "candidate" in requested:
        rows = session.scalars(
            select(OpportunityDraftRecord)
            .where(OpportunityDraftRecord.status.in_(("pending", "linked")))
            .order_by(OpportunityDraftRecord.updated_at.desc())
            .limit(candidate_cap)
        ).all()
        for row in rows:
            try:
                discovery = ProjectDiscovery.model_validate(row.discovery)
            except (TypeError, ValueError):
                continue
            if country and discovery.country.casefold() != country.casefold():
                continue
            if sector and discovery.sector.casefold() != sector.casefold():
                continue
            score, matched = _rank(
                query,
                [
                    ("title", discovery.title, 5),
                    ("owner", discovery.owner, 4),
                    ("country", discovery.country, 2),
                    ("sector", discovery.sector, 3),
                    ("stage", discovery.stage, 2),
                    ("summary", discovery.summary, 2),
                    ("source_title", row.source_title, 2),
                    ("publisher", row.publisher, 1),
                ],
            )
            if not score:
                continue
            results.append(
                _result(
                    resource_type="candidate",
                    resource_id=row.id,
                    title=discovery.title,
                    subtitle=f"Candidate · {row.status} · {discovery.country} · {discovery.sector}",
                    snippet=_snippet(discovery.summary, query),
                    relevance_score=score,
                    matched_fields=matched,
                    metadata={"status": row.status, "owner": discovery.owner},
                )
            )

    if "entity" in requested:
        alias_ids = select(EntityAliasRecord.entity_id).where(
            or_(*_like_clauses((EntityAliasRecord.alias,), query))
        )
        clauses = _like_clauses(
            (EntityRecord.canonical_name, EntityRecord.country), query
        )
        entity_statement = select(EntityRecord).where(
            or_(*(clauses + [EntityRecord.id.in_(alias_ids)]))
        )
        if country:
            entity_statement = entity_statement.where(EntityRecord.country.ilike(country))
        if entity_role:
            entity_statement = entity_statement.where(
                EntityRecord.id.in_(
                    select(OpportunityEntityLinkRecord.entity_id).where(
                        OpportunityEntityLinkRecord.role == entity_role
                    )
                )
            )
        entities = session.scalars(entity_statement.limit(candidate_cap)).all()
        entity_ids = [row.id for row in entities]
        aliases_by_entity: dict[str, list[str]] = defaultdict(list)
        if entity_ids:
            for alias in session.scalars(
                select(EntityAliasRecord).where(EntityAliasRecord.entity_id.in_(entity_ids))
            ).all():
                aliases_by_entity[alias.entity_id].append(alias.alias)
        for row in entities:
            aliases = aliases_by_entity[row.id]
            score, matched = _rank(
                query,
                [
                    ("canonical_name", row.canonical_name, 5),
                    ("country", row.country, 2),
                    *[("alias", alias, 4) for alias in aliases],
                ],
            )
            if not score:
                continue
            link_count = session.scalar(
                select(OpportunityEntityLinkRecord.id)
                .where(OpportunityEntityLinkRecord.entity_id == row.id)
                .limit(1)
            )
            results.append(
                _result(
                    resource_type="entity",
                    resource_id=row.id,
                    title=row.canonical_name,
                    subtitle=f"{row.entity_type} · {row.country or 'Country unknown'}",
                    snippet=("Aliases: " + ", ".join(aliases[:5])) if aliases else row.canonical_name,
                    relevance_score=score,
                    matched_fields=matched,
                    metadata={"status": row.status, "has_opportunity_links": link_count is not None},
                )
            )

    if "evidence" in requested:
        clauses = _like_clauses(
            (
                EvidenceRecord.fact,
                EvidenceRecord.title,
                EvidenceRecord.publisher,
                EvidenceRecord.field_name,
            ),
            query,
        )
        statement = select(EvidenceRecord)
        if clauses:
            statement = statement.where(or_(*clauses))
        if source_rank:
            statement = statement.where(EvidenceRecord.rank == source_rank)
        if country or sector:
            filtered_opportunities = select(OpportunityRecord.id)
            if country:
                filtered_opportunities = filtered_opportunities.where(
                    OpportunityRecord.country.ilike(country)
                )
            if sector:
                filtered_opportunities = filtered_opportunities.where(
                    OpportunityRecord.sector.ilike(sector)
                )
            statement = statement.where(
                EvidenceRecord.opportunity_id.in_(filtered_opportunities)
            )
        rows = session.scalars(statement.limit(candidate_cap)).all()
        for row in rows:
            score, matched = _rank(
                query,
                [
                    ("fact", row.fact, 5),
                    ("title", row.title, 3),
                    ("publisher", row.publisher, 2),
                    ("field_name", row.field_name, 2),
                ],
            )
            if not score:
                continue
            results.append(
                _result(
                    resource_type="evidence",
                    resource_id=row.id,
                    title=row.title,
                    subtitle=f"Evidence {row.rank} · {row.publisher}",
                    snippet=_snippet(row.fact, query),
                    relevance_score=score,
                    matched_fields=matched,
                    opportunity_id=row.opportunity_id,
                    metadata={
                        "field_name": row.field_name,
                        "confidence": row.confidence,
                        "source_url": row.source_url,
                    },
                )
            )

    if "source" in requested:
        clauses = _like_clauses(
            (SourceRecord.title, SourceRecord.publisher, SourceRecord.url), query
        )
        statement = select(SourceRecord)
        if clauses:
            statement = statement.where(or_(*clauses))
        if source_rank:
            statement = statement.where(SourceRecord.source_rank == source_rank)
        if country or sector:
            filtered_opportunities = select(OpportunityRecord.id)
            if country:
                filtered_opportunities = filtered_opportunities.where(
                    OpportunityRecord.country.ilike(country)
                )
            if sector:
                filtered_opportunities = filtered_opportunities.where(
                    OpportunityRecord.sector.ilike(sector)
                )
            statement = statement.where(SourceRecord.opportunity_id.in_(filtered_opportunities))
        rows = session.scalars(statement.limit(candidate_cap)).all()
        for row in rows:
            score, matched = _rank(
                query,
                [
                    ("title", row.title, 5),
                    ("publisher", row.publisher, 3),
                    ("url", row.url, 1),
                ],
            )
            if not score:
                continue
            results.append(
                _result(
                    resource_type="source",
                    resource_id=row.id,
                    title=row.title,
                    subtitle=f"Source {row.source_rank} · {row.publisher}",
                    snippet=row.url or row.title,
                    relevance_score=score,
                    matched_fields=matched,
                    opportunity_id=row.opportunity_id,
                    metadata={"published_at": row.published_at, "url": row.url},
                )
            )

    results.sort(
        key=lambda item: (
            -item["relevance_score"],
            {"opportunity": 0, "entity": 1, "candidate": 2, "evidence": 3, "source": 4}.get(
                item["resource_type"], 9
            ),
            item["title"].casefold(),
        )
    )
    return {
        "query": query,
        "filters": {
            "resource_types": sorted(requested),
            "country": country,
            "sector": sector,
            "entity_role": entity_role,
            "source_rank": source_rank,
        },
        "count": min(len(results), limit),
        "results": results[:limit],
        "note": "relevance_score 仅表示确定性检索相关度，不代表中标概率、项目质量或经营评分。",
    }


def opportunity_knowledge_view(
    session: Session,
    opportunity_id: str,
    *,
    related_limit: int = 20,
) -> dict:
    opportunity = session.get(OpportunityRecord, opportunity_id)
    if opportunity is None:
        raise ValueError("opportunity not found")

    entity_links = session.scalars(
        select(OpportunityEntityLinkRecord)
        .where(OpportunityEntityLinkRecord.opportunity_id == opportunity_id)
        .order_by(OpportunityEntityLinkRecord.role, OpportunityEntityLinkRecord.source_count.desc())
    ).all()
    entity_ids = [item.entity_id for item in entity_links]
    entities_by_id = {
        item.id: item
        for item in (
            session.scalars(select(EntityRecord).where(EntityRecord.id.in_(entity_ids))).all()
            if entity_ids
            else []
        )
    }
    aliases_by_entity: dict[str, list[str]] = defaultdict(list)
    if entity_ids:
        for alias in session.scalars(
            select(EntityAliasRecord).where(EntityAliasRecord.entity_id.in_(entity_ids))
        ).all():
            aliases_by_entity[alias.entity_id].append(alias.alias)

    provenance = session.scalars(
        select(OpportunitySourceDocumentRecord).where(
            OpportunitySourceDocumentRecord.opportunity_id == opportunity_id
        )
    ).all()
    source_doc_by_source = {
        row.source_id: row.source_document_id for row in provenance if row.source_id
    }
    sources = session.scalars(
        select(SourceRecord)
        .where(SourceRecord.opportunity_id == opportunity_id)
        .order_by(SourceRecord.created_at.asc())
    ).all()
    evidence = session.scalars(
        select(EvidenceRecord)
        .where(EvidenceRecord.opportunity_id == opportunity_id)
        .order_by(EvidenceRecord.created_at.asc())
    ).all()
    events = session.scalars(
        select(OpportunityEventRecord)
        .where(OpportunityEventRecord.opportunity_id == opportunity_id)
        .order_by(OpportunityEventRecord.occurred_at.desc())
        .limit(50)
    ).all()

    related: dict[str, dict] = {}
    if entity_ids:
        other_links = session.scalars(
            select(OpportunityEntityLinkRecord).where(
                OpportunityEntityLinkRecord.entity_id.in_(entity_ids),
                OpportunityEntityLinkRecord.opportunity_id != opportunity_id,
            )
        ).all()
        other_ids = list({item.opportunity_id for item in other_links})
        other_opportunities = {
            item.id: item
            for item in (
                session.scalars(select(OpportunityRecord).where(OpportunityRecord.id.in_(other_ids))).all()
                if other_ids
                else []
            )
        }
        for link in other_links:
            other = other_opportunities.get(link.opportunity_id)
            entity = entities_by_id.get(link.entity_id)
            if other is None or entity is None:
                continue
            item = related.setdefault(
                other.id,
                {
                    "opportunity_id": other.id,
                    "title": other.title,
                    "country": other.country,
                    "sector": other.sector,
                    "stage": other.stage,
                    "shared_entities": [],
                },
            )
            item["shared_entities"].append(
                {
                    "entity_id": entity.id,
                    "name": entity.canonical_name,
                    "role_in_related": link.role,
                }
            )

    related_rows = sorted(
        related.values(),
        key=lambda item: (-len(item["shared_entities"]), item["title"].casefold()),
    )[:related_limit]

    return {
        "opportunity": {
            "id": opportunity.id,
            "title": opportunity.title,
            "country": opportunity.country,
            "region": opportunity.region,
            "sector": opportunity.sector,
            "stage": opportunity.stage,
            "owner": opportunity.owner,
            "estimated_value_usd_m": opportunity.estimated_value_usd_m,
            "summary": opportunity.summary,
            "score": opportunity.score,
            "grade": opportunity.grade,
            "confidence": opportunity.confidence,
            "decision": opportunity.decision,
            "pursuit_thesis": opportunity.pursuit_thesis,
            "next_actions": opportunity.next_actions or [],
        },
        "entities": [
            {
                "entity_id": link.entity_id,
                "name": entities_by_id[link.entity_id].canonical_name,
                "country": entities_by_id[link.entity_id].country,
                "role": link.role,
                "confidence": link.confidence,
                "source_count": link.source_count,
                "aliases": aliases_by_entity[link.entity_id][:10],
            }
            for link in entity_links
            if link.entity_id in entities_by_id
        ],
        "sources": [
            {
                "source_id": source.id,
                "source_document_id": source_doc_by_source.get(source.id),
                "title": source.title,
                "publisher": source.publisher,
                "published_at": source.published_at,
                "source_rank": source.source_rank,
                "url": source.url,
            }
            for source in sources
        ],
        "evidence": [
            {
                "evidence_id": item.id,
                "source_id": item.source_id,
                "rank": item.rank,
                "field_name": item.field_name,
                "fact": item.fact,
                "confidence": item.confidence,
                "publisher": item.publisher,
                "source_url": item.source_url,
            }
            for item in evidence
        ],
        "events": [
            {
                "event_type": item.event_type,
                "occurred_at": item.occurred_at.isoformat(),
                "payload": item.payload,
            }
            for item in events
        ],
        "related_opportunities": related_rows,
        "provenance": {
            "formal_source_count": len(sources),
            "immutable_source_document_count": len(provenance),
            "evidence_count": len(evidence),
            "entity_count": len(entity_links),
        },
    }

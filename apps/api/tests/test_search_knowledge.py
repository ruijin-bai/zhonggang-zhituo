from __future__ import annotations

from hashlib import sha256

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import (
    Base,
    EvidenceRecord,
    OpportunityEventRecord,
    OpportunityRecord,
    OrganizationRecord,
    SourceRecord,
    clear_tenant_context,
    set_tenant_context,
    utc_now,
)
from app.intelligence_db import EntityAliasRecord, EntityRecord, OpportunityEntityLinkRecord
from app.opportunity_evidence_db import OpportunitySourceDocumentRecord
from app.search_knowledge import opportunity_knowledge_view, search_knowledge
from app.source_db import SourceDocumentRecord, SourceFetchRecord


def _breakdown() -> dict:
    return {
        "strategic_fit": 10,
        "project_maturity": 8,
        "financing": 7,
        "client_quality": 6,
        "capability_fit": 8,
        "local_position": 5,
        "competition": 5,
        "risk_control": 3,
    }


def _opportunity(opportunity_id: str, *, title: str, owner: str, country: str = "Nigeria"):
    return OpportunityRecord(
        id=opportunity_id,
        title=title,
        country=country,
        region="West Africa",
        sector="港口工程",
        stage="Procurement",
        owner=owner,
        estimated_value_usd_m=450.0,
        summary=f"{title} procurement and financing intelligence.",
        score=52,
        grade="C",
        confidence=72,
        decision="CAUTION",
        breakdown=_breakdown(),
        pursuit_thesis="Track procurement and financing milestones.",
        next_actions=["Verify tender timetable"],
        is_demo=False,
    )


def _entity(entity_id: str, *, name: str, country: str = "Nigeria") -> EntityRecord:
    normalized = " ".join(name.casefold().split())
    country_key = country.casefold()
    return EntityRecord(
        id=entity_id,
        entity_type="organization",
        canonical_name=name,
        normalized_name=normalized,
        country=country,
        country_key=country_key,
        identity_key=sha256(f"organization|{normalized}|{country_key}".encode()).hexdigest(),
        status="active",
        entity_metadata={},
    )


def _engine_and_tenant():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    org = OrganizationRecord(name="Search Tenant A", code="SEARCH-A", is_active=True)
    session.add(org)
    session.commit()
    set_tenant_context(session, org.id)
    return engine, session, org


def test_search_ranks_exact_opportunity_and_keeps_other_tenant_invisible() -> None:
    engine, session, org_a = _engine_and_tenant()
    session.add(
        _opportunity(
            "lagos-port-a",
            title="Lagos Deep Sea Port Expansion",
            owner="Nigerian Ports Authority",
        )
    )
    session.add(
        EvidenceRecord(
            id="evidence-a",
            opportunity_id="lagos-port-a",
            rank="A",
            title="Financing approval notice",
            publisher="Development Bank",
            published_at="2026-08-20",
            fact="Financing approved for Lagos Deep Sea Port Expansion.",
            field_name="financing",
            confidence=0.96,
            source_url="https://example.com/finance",
        )
    )
    session.commit()

    # Seed another tenant without binding the write session to tenant A.
    clear_tenant_context(session)
    org_b = OrganizationRecord(name="Search Tenant B", code="SEARCH-B", is_active=True)
    session.add(org_b)
    session.flush()
    hidden = _opportunity(
        "lagos-port-b",
        title="Lagos Deep Sea Port Expansion",
        owner="Hidden Tenant Owner",
    )
    hidden.organization_id = org_b.id
    session.add(hidden)
    session.commit()
    set_tenant_context(session, org_a.id)

    result = search_knowledge(
        session,
        query="Lagos Deep Sea Port Expansion",
        resource_types={"opportunity", "evidence"},
        limit=20,
    )
    ids = [item["resource_id"] for item in result["results"]]
    assert "lagos-port-a" in ids
    assert "lagos-port-b" not in ids
    assert result["results"][0]["resource_type"] == "opportunity"
    assert result["results"][0]["resource_id"] == "lagos-port-a"
    assert result["results"][0]["relevance_score"] == 100
    assert "title" in result["results"][0]["matched_fields"]
    assert "仅表示确定性检索相关度" in result["note"]
    session.close()
    engine.dispose()


def test_search_supports_entity_alias_chinese_and_structured_filters() -> None:
    engine, session, _ = _engine_and_tenant()
    session.add(
        _opportunity(
            "lekki-access-road",
            title="Lekki Port Access Road",
            owner="Nigerian Ports Authority",
        )
    )
    entity = _entity("npa-entity", name="Nigerian Ports Authority")
    session.add(entity)
    session.flush()
    session.add(
        EntityAliasRecord(
            entity_id=entity.id,
            alias="尼日利亚港务局",
            normalized_alias="尼日利亚港务局",
            source_document_id=None,
            confidence=1.0,
        )
    )
    session.add(
        OpportunityEntityLinkRecord(
            opportunity_id="lekki-access-road",
            entity_id=entity.id,
            role="owner",
            confidence=1.0,
            source_count=2,
            first_seen_at=utc_now(),
            last_seen_at=utc_now(),
        )
    )
    session.commit()

    result = search_knowledge(
        session,
        query="尼日利亚港务局",
        resource_types={"entity"},
        country="Nigeria",
        entity_role="owner",
        limit=10,
    )
    assert result["count"] == 1
    row = result["results"][0]
    assert row["resource_type"] == "entity"
    assert row["resource_id"] == entity.id
    assert "alias" in row["matched_fields"]
    session.close()
    engine.dispose()


def test_opportunity_knowledge_view_keeps_provenance_and_shared_entity_relationships() -> None:
    engine, session, _ = _engine_and_tenant()
    session.add_all(
        [
            _opportunity(
                "port-expansion",
                title="Lagos Port Expansion",
                owner="Nigerian Ports Authority",
            ),
            _opportunity(
                "channel-dredging",
                title="Lagos Access Channel Dredging",
                owner="Nigerian Ports Authority",
            ),
        ]
    )
    entity = _entity("npa-shared", name="Nigerian Ports Authority")
    session.add(entity)
    session.flush()
    session.add_all(
        [
            OpportunityEntityLinkRecord(
                opportunity_id="port-expansion",
                entity_id=entity.id,
                role="owner",
                confidence=1.0,
                source_count=1,
                first_seen_at=utc_now(),
                last_seen_at=utc_now(),
            ),
            OpportunityEntityLinkRecord(
                opportunity_id="channel-dredging",
                entity_id=entity.id,
                role="owner",
                confidence=1.0,
                source_count=1,
                first_seen_at=utc_now(),
                last_seen_at=utc_now(),
            ),
        ]
    )
    fetch = SourceFetchRecord(
        id="fetch-search-doc",
        connector="html",
        source_url="https://example.com/port",
        source_url_hash="a" * 64,
        content_type="text/html",
        raw_sha256="b" * 64,
        raw_size_bytes=100,
        raw_object_key="raw/a",
        storage_backend="s3",
        seen_count=1,
        first_fetched_at=utc_now(),
        last_fetched_at=utc_now(),
    )
    session.add(fetch)
    session.flush()
    document = SourceDocumentRecord(
        id="source-document-search",
        connector="html",
        first_fetch_id=fetch.id,
        latest_fetch_id=fetch.id,
        canonical_url="https://example.com/port/project",
        canonical_url_hash="c" * 64,
        title="Port Expansion Procurement Notice",
        publisher="NPA",
        published_at=utc_now(),
        content_type="text/plain",
        content_sha256="d" * 64,
        text_object_key="text/d",
        storage_backend="s3",
        connector_metadata={},
        seen_count=1,
        first_seen_at=utc_now(),
        last_seen_at=utc_now(),
    )
    session.add(document)
    source = SourceRecord(
        id="formal-source-search",
        opportunity_id="port-expansion",
        title=document.title,
        publisher="NPA",
        published_at="2026-08-20",
        source_rank="A",
        url=document.canonical_url,
        raw_text="Procurement notice body not returned by knowledge view.",
        is_demo=False,
    )
    session.add(source)
    session.flush()
    session.add(
        OpportunitySourceDocumentRecord(
            opportunity_id="port-expansion",
            source_document_id=document.id,
            source_id=source.id,
            linked_at=utc_now(),
        )
    )
    session.add(
        EvidenceRecord(
            id="knowledge-evidence",
            opportunity_id="port-expansion",
            source_id=source.id,
            rank="A",
            title=document.title,
            publisher="NPA",
            published_at="2026-08-20",
            fact="Tender submission is scheduled for Q4 2026.",
            field_name="project_maturity",
            confidence=0.94,
            source_url=document.canonical_url,
        )
    )
    session.add(
        OpportunityEventRecord(
            opportunity_id="port-expansion",
            event_type="evidence_added",
            payload={"source_id": source.id},
        )
    )
    session.commit()

    view = opportunity_knowledge_view(session, "port-expansion")
    assert view["provenance"] == {
        "formal_source_count": 1,
        "immutable_source_document_count": 1,
        "evidence_count": 1,
        "entity_count": 1,
    }
    assert view["sources"][0]["source_document_id"] == document.id
    assert "raw_text" not in view["sources"][0]
    assert view["evidence"][0]["fact"].startswith("Tender submission")
    assert view["events"][0]["event_type"] == "evidence_added"
    assert len(view["related_opportunities"]) == 1
    related = view["related_opportunities"][0]
    assert related["opportunity_id"] == "channel-dredging"
    assert related["shared_entities"][0]["name"] == "Nigerian Ports Authority"
    session.close()
    engine.dispose()


def test_knowledge_view_cannot_read_other_tenant_opportunity() -> None:
    engine, session, org_a = _engine_and_tenant()
    clear_tenant_context(session)
    org_b = OrganizationRecord(name="Knowledge Tenant B", code="KNOW-B", is_active=True)
    session.add(org_b)
    session.flush()
    hidden = _opportunity(
        "hidden-knowledge-opportunity",
        title="Hidden Port Project",
        owner="Hidden Owner",
    )
    hidden.organization_id = org_b.id
    session.add(hidden)
    session.commit()
    set_tenant_context(session, org_a.id)

    with pytest.raises(ValueError, match="opportunity not found"):
        opportunity_knowledge_view(session, hidden.id)
    session.close()
    engine.dispose()

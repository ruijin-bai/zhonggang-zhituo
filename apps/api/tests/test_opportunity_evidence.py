import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.candidate_pipeline import claim_candidate_processing, process_candidate_document
from app.connectors.base import ConnectorResult, build_document
from app.db import (
    Base,
    OpportunityDraftRecord,
    OpportunityRecord,
    OrganizationRecord,
    SourceRecord,
    set_tenant_context,
)
from app.discovery import confirm_draft
from app.document_store import LocalDocumentStore
from app.intelligence_db import EntityRecord, OpportunityEntityLinkRecord, SourceEntityMentionRecord
from app.models import ConfirmDraftRequest, ProjectDiscovery, ProjectParty
from app.opportunity_evidence import (
    attach_candidate_to_opportunity,
    link_opportunity_source_document,
)
from app.opportunity_evidence_db import OpportunitySourceDocumentRecord
from app.source_archive import archive_connector_result


def _settings():
    return SimpleNamespace(
        candidate_dispatch_interval_seconds=10,
        candidate_lease_seconds=300,
        candidate_max_attempts=3,
        candidate_max_backoff_seconds=300,
        candidate_dispatch_batch_size=50,
        candidate_draft_duplicate_threshold=0.88,
    )


def _tenant_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    organization = OrganizationRecord(name="Evidence Tenant", code="EVIDENCE", is_active=True)
    session.add(organization)
    session.commit()
    set_tenant_context(session, organization.id)
    return engine, session


def _archive(session: Session, store: LocalDocumentStore, *, title: str, text: str, url: str):
    raw = f"<html><head><title>{title}</title></head><body>{text}</body></html>".encode()
    document = build_document(
        connector="html",
        canonical_url=url,
        title=title,
        text=text,
        content_type="text/html",
        raw=raw,
        publisher="Procurement Authority",
    )
    result = ConnectorResult(
        connector="html",
        source_url=url,
        source_content_type="text/html",
        source_raw_sha256=document.raw_sha256,
        source_raw_size_bytes=len(raw),
        documents=[document],
        raw_objects={document.raw_sha256: raw},
    )
    return archive_connector_result(result, session, store=store)


def _project(*, owner: str = "Nigerian Ports Authority") -> ProjectDiscovery:
    return ProjectDiscovery(
        project_detected=True,
        title="Lagos Port Expansion Project",
        country="Nigeria",
        region="West Africa",
        sector="港口工程",
        stage="Procurement",
        owner=owner,
        estimated_value_usd_m=450.0,
        summary="Specific port expansion procurement opportunity.",
        confidence=0.86,
        facts=[],
        parties=[
            ProjectParty(
                role="owner",
                name=owner,
                country="Nigeria",
                evidence_quote=f"Owner: {owner}",
                confidence=0.96,
            ),
            ProjectParty(
                role="financier",
                name="African Development Bank",
                country="Nigeria",
                evidence_quote="Financier: African Development Bank",
                confidence=0.91,
            ),
        ],
    )


class FakeAI:
    def __init__(self, discovery: ProjectDiscovery):
        self.discovery = discovery

    async def discover_project(self, text, *, page_title, use_ai=True):
        return self.discovery, "deterministic"


def _process_one(session, store, discovery):
    claim = claim_candidate_processing(session, limit=1)[0]
    return asyncio.run(
        process_candidate_document(
            session,
            claim[0],
            lease_token=claim[1],
            store=store,
            ai_service=FakeAI(discovery),
        )
    )


def test_confirm_then_attach_later_candidate_builds_one_formal_multi_source_chain(monkeypatch, tmp_path):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", _settings)
    engine, session = _tenant_session()
    store = LocalDocumentStore(tmp_path)

    first = _archive(
        session,
        store,
        title="Lagos Port Expansion Project",
        text="First procurement publication " + ("A" * 120),
        url="https://8.8.8.8/source-a/lagos-port",
    )
    first_result = _process_one(session, store, _project())
    confirmed = confirm_draft(
        first_result.draft_id,
        ConfirmDraftRequest(),
        session,
        store=store,
    )
    opportunity_id = confirmed.opportunity.id
    assert session.scalar(
        select(func.count()).select_from(OpportunitySourceDocumentRecord).where(
            OpportunitySourceDocumentRecord.opportunity_id == opportunity_id
        )
    ) == 1

    second = _archive(
        session,
        store,
        title="Lagos Port Expansion Project",
        text="Later independent procurement update " + ("B" * 120),
        url="https://8.8.8.8/source-b/lagos-port",
    )
    second_result = _process_one(session, store, _project())
    assert second_result.status == "candidate_created"
    assert second_result.draft_id != first_result.draft_id

    attached = attach_candidate_to_opportunity(
        session,
        draft_id=second_result.draft_id,
        opportunity_id=opportunity_id,
        store=store,
    )
    session.commit()
    assert attached["status"] == "linked"
    assert attached["attached_count"] == 1
    assert session.get(OpportunityDraftRecord, second_result.draft_id).status == "linked"
    assert session.scalar(
        select(func.count()).select_from(SourceRecord).where(
            SourceRecord.opportunity_id == opportunity_id
        )
    ) == 2
    assert session.scalar(
        select(func.count()).select_from(OpportunitySourceDocumentRecord).where(
            OpportunitySourceDocumentRecord.opportunity_id == opportunity_id
        )
    ) == 2
    assert {first.documents[0].id, second.documents[0].id} == set(
        session.scalars(
            select(OpportunitySourceDocumentRecord.source_document_id).where(
                OpportunitySourceDocumentRecord.opportunity_id == opportunity_id
            )
        ).all()
    )

    entity_links = session.scalars(
        select(OpportunityEntityLinkRecord).where(
            OpportunityEntityLinkRecord.opportunity_id == opportunity_id
        )
    ).all()
    assert {item.role for item in entity_links} == {"owner", "financier"}
    assert all(item.source_count == 2 for item in entity_links)
    session.close()
    engine.dispose()


def test_human_reviewed_owner_controls_formal_entity_link_without_erasing_source_mention(monkeypatch, tmp_path):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", _settings)
    engine, session = _tenant_session()
    store = LocalDocumentStore(tmp_path)
    archived = _archive(
        session,
        store,
        title="Lagos Port Expansion Project",
        text="Owner stated in source " + ("C" * 120),
        url="https://8.8.8.8/source-owner/lagos-port",
    )
    result = _process_one(session, store, _project(owner="Legacy Port Authority"))
    confirmed = confirm_draft(
        result.draft_id,
        ConfirmDraftRequest(owner="Reviewed Port Authority"),
        session,
        store=store,
    )

    owner_links = session.scalars(
        select(OpportunityEntityLinkRecord).where(
            OpportunityEntityLinkRecord.opportunity_id == confirmed.opportunity.id,
            OpportunityEntityLinkRecord.role == "owner",
        )
    ).all()
    assert len(owner_links) == 1
    formal_owner = session.get(EntityRecord, owner_links[0].entity_id)
    assert formal_owner.canonical_name == "Reviewed Port Authority"
    assert owner_links[0].source_count == 0

    source_owner_mentions = session.scalars(
        select(SourceEntityMentionRecord).where(
            SourceEntityMentionRecord.source_document_id == archived.documents[0].id,
            SourceEntityMentionRecord.role == "owner",
        )
    ).all()
    assert len(source_owner_mentions) == 1
    source_owner = session.get(EntityRecord, source_owner_mentions[0].entity_id)
    assert source_owner.canonical_name == "Legacy Port Authority"
    session.close()
    engine.dispose()


def test_one_source_document_cannot_be_linked_to_two_formal_opportunities(monkeypatch, tmp_path):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", _settings)
    engine, session = _tenant_session()
    store = LocalDocumentStore(tmp_path)
    archived = _archive(
        session,
        store,
        title="Lagos Port Expansion Project",
        text="Specific procurement notice " + ("D" * 120),
        url="https://8.8.8.8/source-single/lagos-port",
    )
    result = _process_one(session, store, _project())
    confirmed = confirm_draft(result.draft_id, ConfirmDraftRequest(), session, store=store)

    other = OpportunityRecord(
        id="other-formal-opportunity",
        title="Other Project",
        country="Nigeria",
        region="West Africa",
        sector="港口工程",
        stage="Procurement",
        owner="Other Authority",
        estimated_value_usd_m=None,
        summary="Other formal opportunity",
        score=0,
        grade="D",
        confidence=20,
        decision="INSUFFICIENT_EVIDENCE",
        breakdown={
            "strategic_fit": 0,
            "project_maturity": 0,
            "financing": 0,
            "client_quality": 0,
            "capability_fit": 0,
            "local_position": 0,
            "competition": 0,
            "risk_control": 0,
        },
        pursuit_thesis="",
        next_actions=[],
        is_demo=False,
    )
    session.add(other)
    session.flush()
    with pytest.raises(ValueError, match="其他正式 Opportunity"):
        link_opportunity_source_document(
            session,
            opportunity_id=other.id,
            source_document_id=archived.documents[0].id,
            source_id=None,
        )
    session.rollback()
    assert confirmed.opportunity.id != other.id
    session.close()
    engine.dispose()

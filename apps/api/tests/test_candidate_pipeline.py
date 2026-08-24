import asyncio
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.candidate_db import CandidateProcessingRecord
from app.candidate_pipeline import (
    claim_candidate_processing,
    process_candidate_document,
)
from app.connectors.base import ConnectorResult, build_document
from app.db import (
    Base,
    OpportunityDraftRecord,
    OrganizationRecord,
    SourceRecord,
    set_tenant_context,
    utc_now,
)
from app.discovery import confirm_draft
from app.document_store import LocalDocumentStore
from app.intelligence_db import (
    CandidateSourceDocumentRecord,
    EntityRecord,
    OpportunityEntityLinkRecord,
    SourceDocumentInsightRecord,
    SourceEntityMentionRecord,
)
from app.models import ConfirmDraftRequest, ProjectDiscovery, ProjectParty
from app.source_archive import archive_connector_result


def _settings(**overrides):
    values = {
        "candidate_dispatch_interval_seconds": 10,
        "candidate_lease_seconds": 300,
        "candidate_max_attempts": 3,
        "candidate_max_backoff_seconds": 300,
        "candidate_dispatch_batch_size": 50,
        "candidate_draft_duplicate_threshold": 0.88,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _tenant_session(code: str):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    organization = OrganizationRecord(name=f"Candidate {code}", code=code, is_active=True)
    session.add(organization)
    session.commit()
    set_tenant_context(session, organization.id)
    return engine, session, organization.id


def _archive(
    session: Session,
    store: LocalDocumentStore,
    *,
    title: str,
    text: str,
    url: str,
):
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


class FakeAI:
    def __init__(self, discovery: ProjectDiscovery):
        self.discovery = discovery

    async def discover_project(self, text, *, page_title, use_ai=True):
        return self.discovery, "deterministic"


def _project(title: str, *, detected: bool = True, country: str = "Nigeria") -> ProjectDiscovery:
    parties = []
    if detected:
        parties = [
            ProjectParty(
                role="owner",
                name="Nigerian Ports Authority",
                country=country,
                evidence_quote="Owner: Nigerian Ports Authority",
                confidence=0.94,
            ),
            ProjectParty(
                role="financier",
                name="World Bank",
                country=None,
                evidence_quote="Financier: World Bank",
                confidence=0.91,
            ),
        ]
    return ProjectDiscovery(
        project_detected=detected,
        title=title,
        country=country if detected else "待识别",
        region="West Africa" if detected else "待识别",
        sector="港口工程" if detected else "待识别",
        stage="Procurement" if detected else "待核实",
        owner="Nigerian Ports Authority" if detected else "待识别",
        estimated_value_usd_m=450.0 if detected else None,
        summary="Specific port expansion procurement opportunity." if detected else "Policy article only.",
        confidence=0.86 if detected else 0.2,
        facts=[],
        parties=parties,
    )


def test_new_source_document_creates_durable_candidate_and_human_confirm_reads_object_store(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", lambda: _settings())
    engine, session, _ = _tenant_session("CAND-A")
    store = LocalDocumentStore(tmp_path)
    source_text = "Nigeria port expansion project procurement notice " + ("A" * 120)
    archived = _archive(
        session,
        store,
        title="Lagos Port Expansion Project",
        text=source_text,
        url="https://8.8.8.8/projects/lagos-port",
    )
    document_id = archived.documents[0].id

    processing = session.get(CandidateProcessingRecord, document_id)
    assert processing is not None
    assert processing.status == "pending"
    assert processing.source_document_id == document_id

    claims = claim_candidate_processing(session)
    assert len(claims) == 1
    processing_id, lease_token = claims[0]
    result = asyncio.run(
        process_candidate_document(
            session,
            processing_id,
            lease_token=lease_token,
            store=store,
            ai_service=FakeAI(_project("Lagos Port Expansion Project")),
        )
    )

    assert result.status == "candidate_created"
    assert result.draft_id
    draft = session.get(OpportunityDraftRecord, result.draft_id)
    assert draft is not None
    assert draft.status == "pending"
    assert draft.raw_text == ""
    assert draft.source_url == "https://8.8.8.8/projects/lagos-port"
    assert session.get(SourceDocumentInsightRecord, document_id) is not None
    assert session.scalar(
        select(func.count()).select_from(CandidateSourceDocumentRecord).where(
            CandidateSourceDocumentRecord.draft_id == draft.id
        )
    ) == 1
    assert session.scalar(select(func.count()).select_from(EntityRecord)) == 2
    assert session.scalar(select(func.count()).select_from(SourceEntityMentionRecord)) == 2

    confirmed = confirm_draft(
        draft.id,
        ConfirmDraftRequest(),
        session,
        store=store,
    )
    assert confirmed.source_bound is True
    source = session.scalar(
        select(SourceRecord).where(SourceRecord.opportunity_id == confirmed.opportunity.id)
    )
    assert source is not None
    assert source.raw_text == source_text
    assert draft.status == "confirmed"
    links = session.scalars(
        select(OpportunityEntityLinkRecord).where(
            OpportunityEntityLinkRecord.opportunity_id == confirmed.opportunity.id
        )
    ).all()
    assert {item.role for item in links} == {"owner", "financier"}
    session.close()
    engine.dispose()


def test_non_project_document_is_terminal_without_candidate_draft(monkeypatch, tmp_path):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", lambda: _settings())
    engine, session, _ = _tenant_session("CAND-B")
    store = LocalDocumentStore(tmp_path)
    archived = _archive(
        session,
        store,
        title="Infrastructure policy outlook",
        text="General macro policy commentary without a specific procurement " + ("B" * 100),
        url="https://8.8.8.8/news/policy",
    )
    claims = claim_candidate_processing(session)
    result = asyncio.run(
        process_candidate_document(
            session,
            claims[0][0],
            lease_token=claims[0][1],
            store=store,
            ai_service=FakeAI(_project("Policy", detected=False)),
        )
    )
    assert result.status == "no_project"
    assert result.project_detected is False
    assert session.scalar(select(func.count()).select_from(OpportunityDraftRecord)) == 0
    assert session.get(SourceDocumentInsightRecord, archived.documents[0].id) is not None
    processing = session.get(CandidateProcessingRecord, archived.documents[0].id)
    assert processing.processed_at is not None
    session.close()
    engine.dispose()


def test_repeated_project_from_different_source_is_aggregated_into_one_candidate(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", lambda: _settings())
    engine, session, _ = _tenant_session("CAND-C")
    store = LocalDocumentStore(tmp_path)

    first = _archive(
        session,
        store,
        title="Lagos Port Expansion Project",
        text="First procurement publication for Lagos port expansion " + ("C" * 100),
        url="https://8.8.8.8/source-a/lagos-port",
    )
    first_claim = claim_candidate_processing(session, limit=1)[0]
    first_result = asyncio.run(
        process_candidate_document(
            session,
            first_claim[0],
            lease_token=first_claim[1],
            store=store,
            ai_service=FakeAI(_project("Lagos Port Expansion Project")),
        )
    )
    assert first_result.status == "candidate_created"

    second = _archive(
        session,
        store,
        title="Lagos Port Expansion Project",
        text="Second independent publication for the same Lagos port expansion " + ("D" * 100),
        url="https://8.8.8.8/source-b/lagos-port",
    )
    second_claim = claim_candidate_processing(session, limit=1)[0]
    second_result = asyncio.run(
        process_candidate_document(
            session,
            second_claim[0],
            lease_token=second_claim[1],
            store=store,
            ai_service=FakeAI(_project("Lagos Port Expansion Project")),
        )
    )

    assert second_result.status == "duplicate"
    assert second_result.duplicate_draft_id == first_result.draft_id
    assert session.scalar(select(func.count()).select_from(OpportunityDraftRecord)) == 1
    assert first.documents[0].id != second.documents[0].id
    assert session.scalar(
        select(func.count()).select_from(CandidateSourceDocumentRecord).where(
            CandidateSourceDocumentRecord.draft_id == first_result.draft_id
        )
    ) == 2
    # Exact identity resolution must reuse the same owner/financier entities across both sources.
    assert session.scalar(select(func.count()).select_from(EntityRecord)) == 2
    assert session.scalar(select(func.count()).select_from(SourceEntityMentionRecord)) == 4

    confirmed = confirm_draft(
        first_result.draft_id,
        ConfirmDraftRequest(),
        session,
        store=store,
    )
    assert session.scalar(
        select(func.count()).select_from(SourceRecord).where(
            SourceRecord.opportunity_id == confirmed.opportunity.id
        )
    ) == 2
    entity_links = session.scalars(
        select(OpportunityEntityLinkRecord).where(
            OpportunityEntityLinkRecord.opportunity_id == confirmed.opportunity.id
        )
    ).all()
    assert len(entity_links) == 2
    assert all(item.source_count == 2 for item in entity_links)
    assert "汇聚 2 份来源" in confirmed.note
    session.close()
    engine.dispose()


def test_failed_candidate_processing_retries_then_becomes_terminal(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.candidate_pipeline.get_settings",
        lambda: _settings(candidate_max_attempts=2),
    )
    engine, session, _ = _tenant_session("CAND-D")
    store = LocalDocumentStore(tmp_path)
    archived = _archive(
        session,
        store,
        title="Broken candidate",
        text="Specific road project announcement " + ("E" * 100),
        url="https://8.8.8.8/broken",
    )
    processing_id = archived.documents[0].id
    # Delete the immutable text object to force a real processing failure.
    processing = session.get(CandidateProcessingRecord, processing_id)
    assert processing is not None
    from app.source_db import SourceDocumentRecord

    document = session.get(SourceDocumentRecord, processing_id)
    store._path(document.text_object_key).unlink()

    first_claim = claim_candidate_processing(session)[0]
    first = asyncio.run(
        process_candidate_document(
            session,
            first_claim[0],
            lease_token=first_claim[1],
            store=store,
            ai_service=FakeAI(_project("Broken candidate")),
        )
    )
    assert first.status == "retry"
    row = session.get(CandidateProcessingRecord, processing_id)
    row.next_attempt_at = row.updated_at
    session.commit()

    second_claim = claim_candidate_processing(session)[0]
    second = asyncio.run(
        process_candidate_document(
            session,
            second_claim[0],
            lease_token=second_claim[1],
            store=store,
            ai_service=FakeAI(_project("Broken candidate")),
        )
    )
    assert second.status == "failed"
    assert second.attempts == 2
    assert second.error
    session.close()
    engine.dispose()


def test_stale_candidate_worker_cannot_overwrite_newer_lease(monkeypatch, tmp_path):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", lambda: _settings())
    engine, session, _ = _tenant_session("CAND-E")
    store = LocalDocumentStore(tmp_path)
    archived = _archive(
        session,
        store,
        title="Lease fenced candidate",
        text="Specific bridge project procurement notice " + ("F" * 100),
        url="https://8.8.8.8/lease-fenced",
    )
    processing_id = archived.documents[0].id

    first_claim = claim_candidate_processing(session)[0]
    old_token = first_claim[1]
    row = session.get(CandidateProcessingRecord, processing_id)
    row.lease_until = utc_now() - timedelta(seconds=1)
    session.commit()

    second_claim = claim_candidate_processing(session)[0]
    new_token = second_claim[1]
    assert new_token != old_token

    stale = asyncio.run(
        process_candidate_document(
            session,
            processing_id,
            lease_token=old_token,
            store=store,
            ai_service=FakeAI(_project("Lease fenced candidate")),
        )
    )
    assert stale.status == "stale_claim"
    row = session.get(CandidateProcessingRecord, processing_id)
    assert row.status == "processing"
    assert row.lease_token == new_token
    assert row.attempts == 0
    assert session.scalar(select(func.count()).select_from(OpportunityDraftRecord)) == 0
    session.close()
    engine.dispose()

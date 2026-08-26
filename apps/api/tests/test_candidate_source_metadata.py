import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.candidate_pipeline import claim_candidate_processing, process_candidate_document
from app.connectors.base import ConnectorResult, build_document
from app.db import Base, OpportunityDraftRecord, OrganizationRecord, set_tenant_context
from app.document_store import LocalDocumentStore
from app.intelligence_db import SourceDocumentInsightRecord
from app.models import ProjectDiscovery
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


class FakeAI:
    async def discover_project(self, text, *, page_title, use_ai=True):
        return (
            ProjectDiscovery(
                project_detected=True,
                title=page_title,
                country="待识别",
                region="待识别",
                sector="公路工程",
                stage="Procurement",
                owner="待识别",
                estimated_value_usd_m=None,
                summary="Specific procurement opportunity.",
                confidence=0.78,
                facts=[],
                parties=[],
            ),
            "deterministic",
        )


def test_candidate_uses_authoritative_connector_country_when_extraction_is_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", _settings)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    org = OrganizationRecord(name="Source Metadata Pilot", code="SRC-META", is_active=True)
    session.add(org)
    session.commit()
    set_tenant_context(session, org.id)

    raw = b"World Bank procurement notice for a road rehabilitation project"
    document = build_document(
        connector="worldbank_procurement",
        canonical_url="https://projects.worldbank.org/en/projects-operations/procurement-detail/OP00399999",
        title="Road rehabilitation procurement",
        text=raw.decode(),
        content_type="application/json",
        raw=raw,
        publisher="World Bank Group",
        metadata={"country": "Zambia", "notice_id": "OP00399999"},
    )
    result = ConnectorResult(
        connector="worldbank_procurement",
        source_url="https://search.worldbank.org/api/v2/procnotices?format=json&project_ctry_name=Zambia",
        source_content_type="application/json",
        source_raw_sha256=document.raw_sha256,
        source_raw_size_bytes=len(raw),
        documents=[document],
        raw_objects={document.raw_sha256: raw},
    )
    store = LocalDocumentStore(tmp_path)
    archived = archive_connector_result(result, session, store=store)
    document_id = archived.documents[0].id

    processing_id, lease_token = claim_candidate_processing(session)[0]
    processed = asyncio.run(
        process_candidate_document(
            session,
            processing_id,
            lease_token=lease_token,
            store=store,
            ai_service=FakeAI(),
        )
    )

    assert processed.status == "candidate_created"
    draft = session.get(OpportunityDraftRecord, processed.draft_id)
    assert draft is not None
    assert draft.discovery["country"] == "Zambia"
    insight = session.get(SourceDocumentInsightRecord, document_id)
    assert insight is not None
    assert insight.discovery["country"] == "Zambia"

    session.close()
    engine.dispose()

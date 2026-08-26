import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.candidate_pipeline import claim_candidate_processing, process_candidate_document
from app.connectors.base import ConnectorResult, build_document
from app.db import Base, OpportunityDraftRecord, OrganizationRecord, set_tenant_context
from app.document_store import LocalDocumentStore
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
    def __init__(self, sector: str):
        self.sector = sector

    async def discover_project(self, text, *, page_title, use_ai=True):
        return (
            ProjectDiscovery(
                project_detected=True,
                title=page_title,
                country="待识别",
                region="待识别",
                sector=self.sector,
                stage="Procurement",
                owner="待识别",
                estimated_value_usd_m=None,
                summary="World Bank procurement notice.",
                confidence=0.78,
                facts=[],
                parties=[],
            ),
            "deterministic",
        )


def _session(code: str):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    org = OrganizationRecord(name=f"Procurement Scope {code}", code=code, is_active=True)
    session.add(org)
    session.commit()
    set_tenant_context(session, org.id)
    return engine, session


def _archive_cs(session: Session, store: LocalDocumentStore, *, suffix: str):
    raw = f"World Bank consulting notice {suffix}".encode()
    document = build_document(
        connector="worldbank_procurement",
        canonical_url=f"https://search.worldbank.org/api/v2/procnotices?format=json&id={suffix}",
        title=f"Consulting notice {suffix}",
        text=raw.decode(),
        content_type="application/json",
        raw=raw,
        publisher="World Bank Group",
        metadata={"country": "Zambia", "procurement_group": "CS", "notice_id": suffix},
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
    archive_connector_result(result, session, store=store)


def _process(session: Session, store: LocalDocumentStore, *, sector: str):
    processing_id, lease_token = claim_candidate_processing(session)[0]
    return asyncio.run(
        process_candidate_document(
            session,
            processing_id,
            lease_token=lease_token,
            store=store,
            ai_service=FakeAI(sector),
        )
    )


def test_consulting_notice_without_engineering_sector_stays_out_of_candidate_inbox(monkeypatch, tmp_path):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", _settings)
    engine, session = _session("CS-NONENG")
    store = LocalDocumentStore(tmp_path)
    _archive_cs(session, store, suffix="NONENG")

    result = _process(session, store, sector="待识别")

    assert result.status == "no_project"
    assert result.project_detected is False
    assert session.scalar(select(func.count()).select_from(OpportunityDraftRecord)) == 0
    session.close()
    engine.dispose()


def test_consulting_notice_with_engineering_sector_remains_candidate(monkeypatch, tmp_path):
    monkeypatch.setattr("app.candidate_pipeline.get_settings", _settings)
    engine, session = _session("CS-ROAD")
    store = LocalDocumentStore(tmp_path)
    _archive_cs(session, store, suffix="ROAD")

    result = _process(session, store, sector="公路工程")

    assert result.status == "candidate_created"
    draft = session.get(OpportunityDraftRecord, result.draft_id)
    assert draft is not None
    assert draft.discovery["country"] == "Zambia"
    assert draft.discovery["sector"] == "公路工程"
    session.close()
    engine.dispose()

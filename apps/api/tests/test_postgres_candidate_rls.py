import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.candidate_db import CandidateProcessingRecord
from app.config import get_settings
from app.db import OrganizationRecord, utc_now
from app.source_db import SourceDocumentRecord, SourceFetchRecord


settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.database_url.startswith("postgresql"),
    reason="PostgreSQL RLS integration test requires PostgreSQL",
)


def _source_records(*, suffix: str, organization_id: str, marker: str):
    now = utc_now()
    fetch_id = f"fetch-candidate-{marker}-{suffix}"
    document_id = f"doc-candidate-{marker}-{suffix}"
    fetch = SourceFetchRecord(
        id=fetch_id,
        organization_id=organization_id,
        connector="html",
        source_url=f"https://example.com/{marker}/{suffix}",
        source_url_hash=(marker * 64)[:64],
        content_type="text/html",
        raw_sha256=((marker + "1") * 64)[:64],
        raw_size_bytes=128,
        raw_object_key=f"raw/{marker}/{suffix}",
        storage_backend="s3",
        seen_count=1,
        first_fetched_at=now,
        last_fetched_at=now,
    )
    document = SourceDocumentRecord(
        id=document_id,
        organization_id=organization_id,
        connector="html",
        first_fetch_id=fetch_id,
        latest_fetch_id=fetch_id,
        canonical_url=f"https://example.com/{marker}/{suffix}/project",
        canonical_url_hash=((marker + "2") * 64)[:64],
        title=f"Candidate Project {marker}",
        publisher="Procurement Authority",
        published_at=now,
        content_type="text/plain",
        content_sha256=((marker + "3") * 64)[:64],
        text_object_key=f"text/{marker}/{suffix}",
        storage_backend="s3",
        connector_metadata={},
        seen_count=1,
        first_seen_at=now,
        last_seen_at=now,
    )
    processing = CandidateProcessingRecord(
        id=document_id,
        organization_id=organization_id,
        source_document_id=document_id,
        status="pending",
        draft_id=None,
        duplicate_draft_id=None,
        project_detected=None,
        extraction_mode=None,
        attempts=0,
        next_attempt_at=now,
        lease_until=None,
        lease_token=None,
        error_detail=None,
        created_at=now,
        updated_at=now,
        processed_at=None,
    )
    return fetch, document, processing


def test_postgres_rls_blocks_cross_tenant_candidate_processing_reads_and_writes() -> None:
    suffix = uuid.uuid4().hex[:8]
    org_a = f"candidate-rls-org-a-{suffix}"
    org_b = f"candidate-rls-org-b-{suffix}"
    role = f"zhituo_candidate_rls_{suffix}"
    password = f"CandidateRls-{suffix}-Password-123!"
    fetch_a, doc_a, candidate_a = _source_records(
        suffix=suffix,
        organization_id=org_a,
        marker="a",
    )
    fetch_b, doc_b, candidate_b = _source_records(
        suffix=suffix,
        organization_id=org_b,
        marker="b",
    )
    fetch_a_id, fetch_b_id = fetch_a.id, fetch_b.id
    doc_a_id, doc_b_id = doc_a.id, doc_b.id
    candidate_a_id, candidate_b_id = candidate_a.id, candidate_b.id

    admin_engine = create_engine(settings.database_url, pool_pre_ping=True)
    runtime_engine = None
    role_created = False
    try:
        with Session(admin_engine) as session:
            session.add_all(
                [
                    OrganizationRecord(
                        id=org_a,
                        name=f"Candidate RLS Org A {suffix}",
                        code=f"CAN-A-{suffix}",
                        is_active=True,
                    ),
                    OrganizationRecord(
                        id=org_b,
                        name=f"Candidate RLS Org B {suffix}",
                        code=f"CAN-B-{suffix}",
                        is_active=True,
                    ),
                ]
            )
            session.flush()
            session.add_all([fetch_a, fetch_b])
            session.flush()
            session.add_all([doc_a, doc_b])
            session.flush()
            session.add_all([candidate_a, candidate_b])
            session.commit()

        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\'')
            role_created = True
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            connection.exec_driver_sql(
                f'GRANT SELECT, INSERT ON TABLE candidate_processing TO "{role}"'
            )

        runtime_url = make_url(settings.database_url).set(username=role, password=password)
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        with runtime_engine.connect() as connection:
            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_a},
            )
            visible = connection.execute(
                text("SELECT id FROM candidate_processing WHERE id IN (:a, :b) ORDER BY id"),
                {"a": candidate_a_id, "b": candidate_b_id},
            ).scalars().all()
            assert visible == [candidate_a_id]

            # Reference org A's visible SourceDocument but attempt to write the candidate row as
            # org B. The only intended rejection boundary here is candidate_processing WITH CHECK.
            with pytest.raises(DBAPIError, match="row-level security"):
                connection.execute(
                    text(
                        """
                        INSERT INTO candidate_processing (
                            id, organization_id, source_document_id, status, attempts,
                            next_attempt_at, created_at, updated_at
                        ) VALUES (
                            :id, :org, :source_document_id, 'pending', 0,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": f"forbidden-{suffix}",
                        "org": org_b,
                        "source_document_id": doc_a_id,
                    },
                )
            connection.rollback()

            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_b},
            )
            visible = connection.execute(
                text("SELECT id FROM candidate_processing WHERE id IN (:a, :b) ORDER BY id"),
                {"a": candidate_a_id, "b": candidate_b_id},
            ).scalars().all()
            assert visible == [candidate_b_id]
    finally:
        if runtime_engine is not None:
            runtime_engine.dispose()
        with admin_engine.begin() as connection:
            if role_created:
                connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            connection.execute(
                text("DELETE FROM candidate_processing WHERE id IN (:a, :b)"),
                {"a": candidate_a_id, "b": candidate_b_id},
            )
            connection.execute(
                text("DELETE FROM source_documents WHERE id IN (:a, :b)"),
                {"a": doc_a_id, "b": doc_b_id},
            )
            connection.execute(
                text("DELETE FROM source_fetches WHERE id IN (:a, :b)"),
                {"a": fetch_a_id, "b": fetch_b_id},
            )
            connection.execute(
                text("DELETE FROM organizations WHERE id IN (:a, :b)"),
                {"a": org_a, "b": org_b},
            )
        admin_engine.dispose()

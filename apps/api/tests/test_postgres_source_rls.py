import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import OrganizationRecord, utc_now
from app.source_db import SourceDocumentRecord, SourceFetchRecord

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.database_url.startswith("postgresql"),
    reason="PostgreSQL RLS integration test requires PostgreSQL",
)


def _source_records(*, suffix: str, organization_id: str, marker: str):
    fetch_id = f"fetch-{marker}-{suffix}"
    document_id = f"doc-{marker}-{suffix}"
    now = utc_now()
    fetch = SourceFetchRecord(
        id=fetch_id,
        organization_id=organization_id,
        connector="html",
        source_url=f"https://example.com/{marker}/{suffix}",
        source_url_hash=(marker * 64)[:64],
        content_type="text/html",
        raw_sha256=(suffix * 8)[:64].ljust(64, marker),
        raw_size_bytes=100,
        raw_object_key=f"raw/sha256/{marker}/{suffix}",
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
        canonical_url=f"https://example.com/project/{marker}/{suffix}",
        canonical_url_hash=(marker.upper() * 64)[:64],
        title=f"Source {marker}",
        publisher="Example",
        published_at=None,
        content_type="text/html",
        content_sha256=(suffix[::-1] * 8)[:64].ljust(64, marker),
        text_object_key=f"text/sha256/{marker}/{suffix}",
        storage_backend="s3",
        connector_metadata={},
        seen_count=1,
        first_seen_at=now,
        last_seen_at=now,
    )
    return fetch, document


def test_postgres_rls_blocks_cross_tenant_source_archive_reads() -> None:
    suffix = uuid.uuid4().hex[:8]
    org_a = f"source-rls-org-a-{suffix}"
    org_b = f"source-rls-org-b-{suffix}"
    role = f"zhituo_source_rls_{suffix}"
    password = f"SourceRls-{suffix}-Password-123!"
    fetch_a, document_a = _source_records(suffix=suffix, organization_id=org_a, marker="a")
    fetch_b, document_b = _source_records(suffix=suffix, organization_id=org_b, marker="b")
    fetch_a_id, fetch_b_id = fetch_a.id, fetch_b.id
    document_a_id, document_b_id = document_a.id, document_b.id

    admin_engine = create_engine(settings.database_url, pool_pre_ping=True)
    runtime_engine = None
    role_created = False
    try:
        with Session(admin_engine) as session:
            session.add_all(
                [
                    OrganizationRecord(id=org_a, name=f"Source RLS Org A {suffix}", code=f"SRC-A-{suffix}", is_active=True),
                    OrganizationRecord(id=org_b, name=f"Source RLS Org B {suffix}", code=f"SRC-B-{suffix}", is_active=True),
                ]
            )
            session.flush()
            session.add_all([fetch_a, fetch_b])
            session.flush()
            session.add_all([document_a, document_b])
            session.commit()

        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\'')
            role_created = True
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            connection.exec_driver_sql(
                f'GRANT SELECT ON TABLE source_fetches, source_documents TO "{role}"'
            )

        runtime_url = make_url(settings.database_url).set(username=role, password=password)
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        with runtime_engine.connect() as connection:
            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_a},
            )
            fetch_ids = connection.execute(
                text("SELECT id FROM source_fetches WHERE id IN (:a, :b) ORDER BY id"),
                {"a": fetch_a_id, "b": fetch_b_id},
            ).scalars().all()
            document_ids = connection.execute(
                text("SELECT id FROM source_documents WHERE id IN (:a, :b) ORDER BY id"),
                {"a": document_a_id, "b": document_b_id},
            ).scalars().all()
            assert fetch_ids == [fetch_a_id]
            assert document_ids == [document_a_id]

            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_b},
            )
            fetch_ids = connection.execute(
                text("SELECT id FROM source_fetches WHERE id IN (:a, :b) ORDER BY id"),
                {"a": fetch_a_id, "b": fetch_b_id},
            ).scalars().all()
            document_ids = connection.execute(
                text("SELECT id FROM source_documents WHERE id IN (:a, :b) ORDER BY id"),
                {"a": document_a_id, "b": document_b_id},
            ).scalars().all()
            assert fetch_ids == [fetch_b_id]
            assert document_ids == [document_b_id]
    finally:
        if runtime_engine is not None:
            runtime_engine.dispose()
        with admin_engine.begin() as connection:
            if role_created:
                connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            connection.execute(
                text("DELETE FROM source_documents WHERE id IN (:a, :b)"),
                {"a": document_a_id, "b": document_b_id},
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

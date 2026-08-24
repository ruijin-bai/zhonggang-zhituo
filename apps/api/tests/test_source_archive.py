from hashlib import sha256

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorResult, build_document
from app.db import Base, OrganizationRecord, set_tenant_context
from app.document_store import LocalDocumentStore
from app.source_archive import archive_connector_result
from app.source_db import SourceDocumentRecord, SourceFetchRecord


def _result(*, text: str, raw: bytes, source_url: str = "https://example.com/source") -> ConnectorResult:
    document = build_document(
        connector="html",
        canonical_url="https://example.com/project/1",
        title="Port Project",
        text=text,
        content_type="text/html",
        raw=raw,
        publisher="Example Authority",
        metadata={"fixture": True},
    )
    raw_digest = sha256(raw).hexdigest()
    return ConnectorResult(
        connector="html",
        source_url=source_url,
        source_content_type="text/html",
        source_raw_sha256=raw_digest,
        source_raw_size_bytes=len(raw),
        documents=[document],
        raw_objects={raw_digest: raw},
    )


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _create_org(session: Session, organization_id: str, code: str) -> None:
    session.add(
        OrganizationRecord(
            id=organization_id,
            name=f"Organization {code}",
            code=code,
            is_active=True,
        )
    )
    session.commit()


def test_archive_is_idempotent_for_same_raw_and_normalized_content(tmp_path) -> None:
    engine = _engine()
    store = LocalDocumentStore(tmp_path)
    result = _result(
        text="International tender for a port terminal and access road.",
        raw=b"<html><body>International tender for a port terminal and access road.</body></html>",
    )

    with Session(engine) as session:
        _create_org(session, "org-a", "ORG-A")
        set_tenant_context(session, "org-a")

        first = archive_connector_result(result, session, store=store)
        second = archive_connector_result(result, session, store=store)

        assert first.fetch_created is True
        assert first.fetch_seen_count == 1
        assert first.documents_created == 1
        assert first.documents[0].seen_count == 1
        assert second.fetch_created is False
        assert second.fetch_seen_count == 2
        assert second.raw_object_created is False
        assert second.text_objects_created == 0
        assert second.documents_created == 0
        assert second.documents[0].seen_count == 2
        assert second.fetch_id == first.fetch_id
        assert second.documents[0].id == first.documents[0].id

        assert session.scalar(select(func.count()).select_from(SourceFetchRecord)) == 1
        assert session.scalar(select(func.count()).select_from(SourceDocumentRecord)) == 1
        fetch = session.scalar(select(SourceFetchRecord))
        document = session.scalar(select(SourceDocumentRecord))
        assert fetch is not None and fetch.seen_count == 2
        assert document is not None and document.seen_count == 2
        assert fetch.last_fetched_at >= fetch.first_fetched_at
        assert document.last_seen_at >= document.first_seen_at

    engine.dispose()


def test_archive_retains_new_versions_when_source_content_changes(tmp_path) -> None:
    engine = _engine()
    store = LocalDocumentStore(tmp_path)
    first_result = _result(
        text="Tender notice version one with initial procurement scope.",
        raw=b"<html>version one with initial procurement scope</html>",
    )
    second_result = _result(
        text="Tender notice version two with revised financing and procurement scope.",
        raw=b"<html>version two with revised financing and procurement scope</html>",
    )

    with Session(engine) as session:
        _create_org(session, "org-a", "ORG-A")
        set_tenant_context(session, "org-a")

        first = archive_connector_result(first_result, session, store=store)
        second = archive_connector_result(second_result, session, store=store)

        assert first.fetch_id != second.fetch_id
        assert first.documents[0].id != second.documents[0].id
        assert second.fetch_created is True
        assert second.documents_created == 1
        assert session.scalar(select(func.count()).select_from(SourceFetchRecord)) == 2
        assert session.scalar(select(func.count()).select_from(SourceDocumentRecord)) == 2

        versions = session.scalars(
            select(SourceDocumentRecord).order_by(SourceDocumentRecord.first_seen_at.asc())
        ).all()
        assert {item.content_sha256 for item in versions} == {
            first_result.documents[0].content_sha256,
            second_result.documents[0].content_sha256,
        }
        assert all(item.seen_count == 1 for item in versions)

    engine.dispose()


def test_archive_deduplication_is_tenant_scoped_while_objects_are_shared(tmp_path) -> None:
    engine = _engine()
    store = LocalDocumentStore(tmp_path)
    result = _result(
        text="Shared public procurement notice with enough normalized content.",
        raw=b"<html>Shared public procurement notice with enough normalized content.</html>",
    )

    with Session(engine) as control:
        _create_org(control, "org-a", "ORG-A")
        _create_org(control, "org-b", "ORG-B")

    with Session(engine) as session_a:
        set_tenant_context(session_a, "org-a")
        archived_a = archive_connector_result(result, session_a, store=store)
        assert session_a.scalar(select(func.count()).select_from(SourceDocumentRecord)) == 1

    with Session(engine) as session_b:
        set_tenant_context(session_b, "org-b")
        archived_b = archive_connector_result(result, session_b, store=store)
        assert session_b.scalar(select(func.count()).select_from(SourceDocumentRecord)) == 1

    assert archived_a.fetch_id != archived_b.fetch_id
    assert archived_a.documents[0].id != archived_b.documents[0].id
    assert archived_a.raw_object_created is True
    assert archived_b.raw_object_created is False

    with Session(engine) as admin:
        assert admin.scalar(select(func.count()).select_from(SourceFetchRecord)) == 2
        assert admin.scalar(select(func.count()).select_from(SourceDocumentRecord)) == 2

    engine.dispose()

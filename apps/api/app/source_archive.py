from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .connectors import ConnectorResult, connector_kinds, fetch_documents
from .document_store import DocumentStore, build_document_store
from .source_db import SourceDocumentRecord, SourceFetchRecord
from .db import utc_now


class SourceFetchRequest(BaseModel):
    connector: str
    url: str = Field(min_length=8, max_length=4000)


class ArchivedDocument(BaseModel):
    id: str
    canonical_url: str
    title: str
    content_sha256: str
    created: bool
    seen_count: int


class SourceArchiveResult(BaseModel):
    connector: str
    source_url: str
    fetch_id: str
    fetch_created: bool
    raw_object_created: bool
    text_objects_created: int
    documents_created: int
    documents_seen: int
    documents: list[ArchivedDocument]


def _url_hash(url: str) -> str:
    return sha256(url.strip().encode("utf-8")).hexdigest()


def _find_fetch(session: Session, result: ConnectorResult) -> SourceFetchRecord | None:
    return session.scalar(
        select(SourceFetchRecord).where(
            SourceFetchRecord.connector == result.connector,
            SourceFetchRecord.source_url_hash == _url_hash(result.source_url),
            SourceFetchRecord.raw_sha256 == result.source_raw_sha256,
        )
    )


def _get_or_create_fetch(
    session: Session,
    result: ConnectorResult,
    *,
    raw_object_key: str,
    storage_backend: str,
) -> tuple[SourceFetchRecord, bool]:
    existing = _find_fetch(session, result)
    if existing is not None:
        return existing, False

    record = SourceFetchRecord(
        id=str(uuid4()),
        connector=result.connector,
        source_url=result.source_url,
        source_url_hash=_url_hash(result.source_url),
        content_type=result.source_content_type,
        raw_sha256=result.source_raw_sha256,
        raw_size_bytes=result.source_raw_size_bytes,
        raw_object_key=raw_object_key,
        storage_backend=storage_backend,
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
        return record, True
    except IntegrityError:
        existing = _find_fetch(session, result)
        if existing is None:
            raise
        return existing, False


def _find_document(session: Session, *, canonical_url: str, content_sha256: str):
    return session.scalar(
        select(SourceDocumentRecord).where(
            SourceDocumentRecord.canonical_url_hash == _url_hash(canonical_url),
            SourceDocumentRecord.content_sha256 == content_sha256,
        )
    )


def _upsert_document(
    session: Session,
    *,
    fetch_record: SourceFetchRecord,
    connector: str,
    document,
    text_object_key: str,
    storage_backend: str,
) -> tuple[SourceDocumentRecord, bool]:
    now = utc_now()
    existing = _find_document(
        session,
        canonical_url=document.canonical_url,
        content_sha256=document.content_sha256,
    )
    if existing is not None:
        existing.latest_fetch_id = fetch_record.id
        existing.last_seen_at = now
        existing.seen_count += 1
        existing.title = document.title
        existing.publisher = document.publisher
        existing.published_at = document.published_at
        existing.connector_metadata = document.metadata
        return existing, False

    record = SourceDocumentRecord(
        id=str(uuid4()),
        connector=connector,
        first_fetch_id=fetch_record.id,
        latest_fetch_id=fetch_record.id,
        canonical_url=document.canonical_url,
        canonical_url_hash=_url_hash(document.canonical_url),
        title=document.title,
        publisher=document.publisher,
        published_at=document.published_at,
        content_type=document.content_type,
        content_sha256=document.content_sha256,
        text_object_key=text_object_key,
        storage_backend=storage_backend,
        connector_metadata=document.metadata,
        seen_count=1,
        first_seen_at=now,
        last_seen_at=now,
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
        return record, True
    except IntegrityError:
        existing = _find_document(
            session,
            canonical_url=document.canonical_url,
            content_sha256=document.content_sha256,
        )
        if existing is None:
            raise
        existing.latest_fetch_id = fetch_record.id
        existing.last_seen_at = now
        existing.seen_count += 1
        return existing, False


def archive_connector_result(
    result: ConnectorResult,
    session: Session,
    *,
    store: DocumentStore | None = None,
) -> SourceArchiveResult:
    if result.connector not in connector_kinds():
        raise ValueError(f"unsupported connector result: {result.connector}")
    raw = result.raw_objects.get(result.source_raw_sha256)
    if raw is None:
        raise ValueError("connector result does not contain its raw source payload")
    if len(raw) != result.source_raw_size_bytes:
        raise ValueError("connector raw payload size does not match metadata")

    resolved_store = store or build_document_store()
    raw_object = resolved_store.put(
        namespace="raw",
        digest=result.source_raw_sha256,
        data=raw,
        content_type=result.source_content_type,
    )
    fetch_record, fetch_created = _get_or_create_fetch(
        session,
        result,
        raw_object_key=raw_object.key,
        storage_backend=raw_object.backend,
    )

    archived_documents: list[ArchivedDocument] = []
    documents_created = 0
    text_objects_created = 0
    for document in result.documents:
        text_bytes = document.text.encode("utf-8")
        text_object = resolved_store.put(
            namespace="text",
            digest=document.content_sha256,
            data=text_bytes,
            content_type="text/plain; charset=utf-8",
        )
        if text_object.created:
            text_objects_created += 1
        record, created = _upsert_document(
            session,
            fetch_record=fetch_record,
            connector=result.connector,
            document=document,
            text_object_key=text_object.key,
            storage_backend=text_object.backend,
        )
        if created:
            documents_created += 1
        archived_documents.append(
            ArchivedDocument(
                id=record.id,
                canonical_url=record.canonical_url,
                title=record.title,
                content_sha256=record.content_sha256,
                created=created,
                seen_count=record.seen_count,
            )
        )

    session.commit()
    return SourceArchiveResult(
        connector=result.connector,
        source_url=result.source_url,
        fetch_id=fetch_record.id,
        fetch_created=fetch_created,
        raw_object_created=raw_object.created,
        text_objects_created=text_objects_created,
        documents_created=documents_created,
        documents_seen=len(archived_documents),
        documents=archived_documents,
    )


async def fetch_and_archive_source(
    request: SourceFetchRequest,
    session: Session,
    *,
    store: DocumentStore | None = None,
) -> SourceArchiveResult:
    result = await fetch_documents(request.connector, request.url)
    return archive_connector_result(result, session, store=store)


def list_archived_documents(session: Session, *, limit: int = 100) -> list[dict]:
    rows = session.scalars(
        select(SourceDocumentRecord)
        .order_by(SourceDocumentRecord.last_seen_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": item.id,
            "connector": item.connector,
            "canonical_url": item.canonical_url,
            "title": item.title,
            "publisher": item.publisher,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "content_sha256": item.content_sha256,
            "text_object_key": item.text_object_key,
            "storage_backend": item.storage_backend,
            "seen_count": item.seen_count,
            "first_seen_at": item.first_seen_at.isoformat(),
            "last_seen_at": item.last_seen_at.isoformat(),
        }
        for item in rows
    ]

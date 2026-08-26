from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .ai import AIService
from .candidate_db import CandidateProcessingRecord
from .config import get_settings
from .db import OpportunityDraftRecord, utc_now
from .document_store import DocumentStore, build_document_store
from .intelligence import (
    link_candidate_source,
    record_document_insight,
    resolve_discovery_entities,
)
from .project_matching import opportunity_duplicate_matches, pending_draft_duplicate
from .source_db import SourceDocumentRecord


class CandidateProcessResult(BaseModel):
    processing_id: str
    source_document_id: str
    status: str
    draft_id: str | None = None
    duplicate_draft_id: str | None = None
    project_detected: bool | None = None
    extraction_mode: str | None = None
    attempts: int
    error: str | None = None


class CandidateSourceSnapshot(BaseModel):
    id: str
    title: str
    canonical_url: str
    publisher: str | None
    published_at: datetime | None
    content_sha256: str
    text_object_key: str
    connector_metadata: dict


def ensure_candidate_processing(session: Session, source_document_id: str) -> CandidateProcessingRecord:
    existing = session.get(CandidateProcessingRecord, source_document_id)
    if existing is not None:
        return existing
    now = utc_now()
    record = CandidateProcessingRecord(
        id=source_document_id,
        source_document_id=source_document_id,
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
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
        return record
    except IntegrityError:
        existing = session.get(CandidateProcessingRecord, source_document_id)
        if existing is None:
            raise
        return existing


def _lease_expired_clause(now):
    return or_(
        CandidateProcessingRecord.lease_until.is_(None),
        CandidateProcessingRecord.lease_until < now,
    )


def claim_candidate_processing(
    session: Session,
    *,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    settings = get_settings()
    now = utc_now()
    rows = session.scalars(
        select(CandidateProcessingRecord)
        .where(
            CandidateProcessingRecord.status.in_(("pending", "retry", "processing")),
            CandidateProcessingRecord.next_attempt_at <= now,
            _lease_expired_clause(now),
        )
        .order_by(CandidateProcessingRecord.next_attempt_at.asc())
        .limit(limit or settings.candidate_dispatch_batch_size)
        .with_for_update(skip_locked=True)
    ).all()
    claims: list[tuple[str, str]] = []
    lease_until = now + timedelta(seconds=settings.candidate_lease_seconds)
    for row in rows:
        token = str(uuid4())
        row.status = "processing"
        row.lease_until = lease_until
        row.lease_token = token
        row.updated_at = now
        claims.append((row.id, token))
    session.commit()
    return claims


def _lock_processing(session: Session, processing_id: str) -> CandidateProcessingRecord | None:
    return session.scalar(
        select(CandidateProcessingRecord)
        .where(CandidateProcessingRecord.id == processing_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def release_candidate_dispatch_claim(
    session: Session,
    processing_id: str,
    error: str,
    *,
    lease_token: str,
) -> None:
    settings = get_settings()
    row = _lock_processing(session, processing_id)
    if row is None:
        session.rollback()
        return
    if row.lease_token != lease_token:
        session.rollback()
        return
    now = utc_now()
    row.status = "retry"
    row.lease_until = None
    row.lease_token = None
    row.error_detail = f"dispatch failed: {error}"[:2000]
    row.next_attempt_at = now + timedelta(seconds=settings.candidate_dispatch_interval_seconds)
    row.updated_at = now
    session.commit()


def _retry_delay(attempts: int) -> int:
    settings = get_settings()
    delay = settings.candidate_dispatch_interval_seconds * (2 ** min(max(attempts - 1, 0), 10))
    return min(delay, settings.candidate_max_backoff_seconds)


def _load_document_text(
    session: Session,
    source_document_id: str,
    *,
    store: DocumentStore | None = None,
) -> tuple[CandidateSourceSnapshot, str]:
    document = session.get(SourceDocumentRecord, source_document_id)
    if document is None:
        raise ValueError("source document not found")
    snapshot = CandidateSourceSnapshot(
        id=document.id,
        title=document.title,
        canonical_url=document.canonical_url,
        publisher=document.publisher,
        published_at=document.published_at,
        content_sha256=document.content_sha256,
        text_object_key=document.text_object_key,
        connector_metadata=document.connector_metadata,
    )

    # SourceDocument metadata is immutable enough for one processing attempt. End the read
    # transaction before S3/object-store and AI network I/O so workers do not pin a PostgreSQL
    # transaction/connection for the whole external call. Session tenant context survives the
    # rollback and db.py restores PostgreSQL set_config on the next transaction.
    session.rollback()

    resolved_store = store or build_document_store()
    raw = resolved_store.get(snapshot.text_object_key)
    actual = sha256(raw).hexdigest()
    if actual != snapshot.content_sha256:
        raise RuntimeError("normalized source document object failed SHA-256 verification")
    text_value = raw.decode("utf-8", errors="strict")
    if not text_value.strip():
        raise ValueError("normalized source document text is empty")
    # Project discovery has a deliberate bounded context. The immutable full text remains in
    # DocumentStore and can be reprocessed later with chunking/retrieval if needed.
    return snapshot, text_value[:100_000]


def _finalization_lock(session: Session) -> None:
    """Serialize candidate dedupe/finalization per organization on PostgreSQL.

    Network/AI work happens before this lock. The short transaction-level advisory lock closes
    the race where two workers detect the same newly announced project from different sources at
    the same time and both see an empty candidate inbox.
    """

    if session.get_bind().dialect.name != "postgresql":
        return
    organization_id = session.info.get("organization_id")
    if not organization_id:
        return
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"zhituo:candidate-finalize:{organization_id}"},
    )


def _result(
    row: CandidateProcessingRecord,
    *,
    status: str | None = None,
) -> CandidateProcessResult:
    return CandidateProcessResult(
        processing_id=row.id,
        source_document_id=row.source_document_id,
        status=status or row.status,
        draft_id=row.draft_id,
        duplicate_draft_id=row.duplicate_draft_id,
        project_detected=row.project_detected,
        extraction_mode=row.extraction_mode,
        attempts=row.attempts,
        error=row.error_detail,
    )


async def process_candidate_document(
    session: Session,
    processing_id: str,
    *,
    lease_token: str,
    store: DocumentStore | None = None,
    ai_service: AIService | None = None,
) -> CandidateProcessResult:
    settings = get_settings()
    row = session.get(CandidateProcessingRecord, processing_id)
    if row is None:
        raise ValueError("candidate processing record not found")
    if row.lease_token != lease_token:
        session.rollback()
        return _result(row, status="stale_claim")
    if row.status not in {"processing", "pending", "retry"}:
        session.rollback()
        return _result(row)

    source_document_id = row.source_document_id
    try:
        document, document_text = _load_document_text(
            session,
            source_document_id,
            store=store,
        )
        service = ai_service or AIService()
        discovery, mode = await service.discover_project(
            document_text,
            page_title=document.title,
            use_ai=True,
        )
        metadata_country = str(document.connector_metadata.get("country") or "").strip()
        if discovery.country == "待识别" and metadata_country:
            discovery = discovery.model_copy(update={"country": metadata_country})
        procurement_group = str(
            document.connector_metadata.get("procurement_group") or ""
        ).strip().upper()
        if (
            mode == "deterministic"
            and discovery.sector == "待识别"
            and procurement_group in {"CS", "NC"}
        ):
            discovery = discovery.model_copy(
                update={
                    "project_detected": False,
                    "confidence": min(discovery.confidence, 0.45),
                    "summary": (
                        "结构化采购分类表明该公告属于咨询/非咨询服务，且当前文本未识别出工程专业；"
                        "保留来源记录但不进入工程项目候选箱。"
                    ),
                }
            )

        # Re-enter a short locked transaction after the expensive external/model call. A stale
        # worker that lost its lease is fenced out before it can create a candidate.
        row = _lock_processing(session, processing_id)
        if row is None:
            session.rollback()
            raise ValueError("candidate processing record disappeared")
        if row.lease_token != lease_token:
            session.rollback()
            return _result(row, status="stale_claim")
        _finalization_lock(session)

        now = utc_now()
        row.attempts += 1
        row.project_detected = discovery.project_detected
        row.extraction_mode = mode
        row.error_detail = None
        row.lease_until = None
        row.lease_token = None
        row.processed_at = now
        row.updated_at = now

        # Persist the structured understanding per immutable SourceDocument. This allows a later
        # candidate confirmation to aggregate every source's facts instead of retaining only the
        # first document that happened to create the draft.
        record_document_insight(
            session,
            source_document_id=source_document_id,
            discovery=discovery,
            extraction_mode=mode,
        )

        if not discovery.project_detected:
            row.status = "no_project"
            session.commit()
            return _result(row)

        resolve_discovery_entities(
            session,
            discovery=discovery,
            source_document_id=source_document_id,
        )

        duplicate = pending_draft_duplicate(
            discovery,
            session,
            threshold=settings.candidate_draft_duplicate_threshold,
        )
        if duplicate is not None:
            row.status = "duplicate"
            row.duplicate_draft_id = duplicate[0]
            link_candidate_source(
                session,
                draft_id=duplicate[0],
                source_document_id=source_document_id,
                is_primary=False,
            )
            existing_draft = session.get(OpportunityDraftRecord, duplicate[0])
            if existing_draft is not None:
                existing_draft.updated_at = now
            session.commit()
            return _result(row)

        draft_id = str(uuid4())
        duplicate_matches = opportunity_duplicate_matches(discovery, session)
        published_at = document.published_at.isoformat() if document.published_at else "待核实"
        session.add(
            OpportunityDraftRecord(
                id=draft_id,
                status="pending",
                discovery=discovery.model_dump(mode="json"),
                source_url=document.canonical_url,
                source_title=document.title,
                publisher=document.publisher or "公开来源",
                published_at=published_at,
                source_rank="B",
                # Full normalized text remains immutable in DocumentStore. The source-link table
                # connects all supporting SourceDocuments to the candidate without copying body
                # text into PostgreSQL.
                raw_text="",
                duplicate_matches=[item.model_dump(mode="json") for item in duplicate_matches],
                is_demo=False,
            )
        )
        session.flush()
        link_candidate_source(
            session,
            draft_id=draft_id,
            source_document_id=source_document_id,
            is_primary=True,
        )
        row.status = "candidate_created"
        row.draft_id = draft_id
        session.commit()
        return _result(row)
    except Exception as exc:
        session.rollback()
        row = _lock_processing(session, processing_id)
        if row is None:
            session.rollback()
            raise
        if row.lease_token != lease_token:
            session.rollback()
            return _result(row, status="stale_claim")
        now = utc_now()
        row.attempts += 1
        row.lease_until = None
        row.lease_token = None
        row.error_detail = f"{type(exc).__name__}: {exc}"[:2000]
        row.updated_at = now
        if row.attempts >= settings.candidate_max_attempts:
            row.status = "failed"
            row.processed_at = now
        else:
            row.status = "retry"
            row.next_attempt_at = now + timedelta(seconds=_retry_delay(row.attempts))
        session.commit()
        return _result(row)


def list_candidate_processing(session: Session, *, limit: int = 200) -> list[dict]:
    rows = session.scalars(
        select(CandidateProcessingRecord)
        .order_by(CandidateProcessingRecord.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "source_document_id": row.source_document_id,
            "status": row.status,
            "draft_id": row.draft_id,
            "duplicate_draft_id": row.duplicate_draft_id,
            "project_detected": row.project_detected,
            "extraction_mode": row.extraction_mode,
            "attempts": row.attempts,
            "next_attempt_at": row.next_attempt_at.isoformat(),
            "error_detail": row.error_detail,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "processed_at": row.processed_at.isoformat() if row.processed_at else None,
        }
        for row in rows
    ]

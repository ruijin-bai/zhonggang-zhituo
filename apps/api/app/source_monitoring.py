from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .connectors import connector_kinds, fetch_documents_conditional
from .db import utc_now
from .document_store import DocumentStore
from .source_archive import archive_connector_result
from .source_db import SourceScanRunRecord, SourceSubscriptionRecord
from .web_fetch import validate_public_url


class SourceSubscriptionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    connector: str
    url: str = Field(min_length=8, max_length=4000)
    interval_seconds: int = 3600


class SourceSubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=240)
    interval_seconds: int | None = None


class SourceScanResult(BaseModel):
    subscription_id: str
    outcome: str
    changed: bool = False
    not_modified: bool = False
    fetch_id: str | None = None
    documents_seen: int = 0
    documents_created: int = 0
    consecutive_failures: int = 0
    next_scan_at: str
    status: str
    error: str | None = None


def _url_hash(url: str) -> str:
    return sha256(url.strip().encode("utf-8")).hexdigest()


def _validated_interval(value: int) -> int:
    settings = get_settings()
    if value < settings.source_scan_min_interval_seconds:
        raise ValueError(
            f"source interval must be at least {settings.source_scan_min_interval_seconds} seconds"
        )
    if value > 31_536_000:
        raise ValueError("source interval cannot exceed one year")
    return value


def subscription_to_dict(item: SourceSubscriptionRecord) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "connector": item.connector,
        "url": item.url,
        "status": item.status,
        "pause_reason": item.pause_reason,
        "interval_seconds": item.interval_seconds,
        "next_scan_at": item.next_scan_at.isoformat(),
        "lease_until": item.lease_until.isoformat() if item.lease_until else None,
        "etag": item.etag,
        "last_modified": item.last_modified,
        "consecutive_failures": item.consecutive_failures,
        "total_scans": item.total_scans,
        "total_changes": item.total_changes,
        "last_scan_at": item.last_scan_at.isoformat() if item.last_scan_at else None,
        "last_success_at": item.last_success_at.isoformat() if item.last_success_at else None,
        "last_changed_at": item.last_changed_at.isoformat() if item.last_changed_at else None,
        "last_outcome": item.last_outcome,
        "last_error": item.last_error,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def scan_run_to_dict(item: SourceScanRunRecord) -> dict:
    return {
        "id": item.id,
        "subscription_id": item.subscription_id,
        "outcome": item.outcome,
        "fetch_id": item.fetch_id,
        "manual": item.manual,
        "not_modified": item.not_modified,
        "documents_seen": item.documents_seen,
        "documents_created": item.documents_created,
        "error_detail": item.error_detail,
        "started_at": item.started_at.isoformat(),
        "finished_at": item.finished_at.isoformat(),
    }


def get_subscription(session: Session, subscription_id: str) -> SourceSubscriptionRecord | None:
    return session.scalar(
        select(SourceSubscriptionRecord).where(SourceSubscriptionRecord.id == subscription_id)
    )


def _lock_subscription(session: Session, subscription_id: str) -> SourceSubscriptionRecord | None:
    return session.scalar(
        select(SourceSubscriptionRecord)
        .where(SourceSubscriptionRecord.id == subscription_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def create_subscription(
    session: Session,
    body: SourceSubscriptionCreate,
) -> SourceSubscriptionRecord:
    connector = body.connector.strip().lower()
    if connector not in connector_kinds():
        raise ValueError(f"unsupported connector: {body.connector}")
    url = validate_public_url(body.url.strip())
    interval = _validated_interval(body.interval_seconds)
    now = utc_now()
    record = SourceSubscriptionRecord(
        id=str(uuid4()),
        name=body.name.strip(),
        connector=connector,
        url=url,
        url_hash=_url_hash(url),
        status="active",
        pause_reason=None,
        interval_seconds=interval,
        next_scan_at=now,
        lease_until=None,
        lease_token=None,
        etag=None,
        last_modified=None,
        consecutive_failures=0,
        total_scans=0,
        total_changes=0,
        last_scan_at=None,
        last_success_at=None,
        last_changed_at=None,
        last_outcome=None,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    try:
        session.add(record)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("this source URL is already subscribed for the connector") from exc
    return record


def update_subscription(
    session: Session,
    subscription_id: str,
    body: SourceSubscriptionUpdate,
) -> SourceSubscriptionRecord:
    record = get_subscription(session, subscription_id)
    if record is None:
        raise ValueError("source subscription not found")
    if body.name is not None:
        record.name = body.name.strip()
    if body.interval_seconds is not None:
        record.interval_seconds = _validated_interval(body.interval_seconds)
        if record.status == "active":
            record.next_scan_at = min(
                record.next_scan_at,
                utc_now() + timedelta(seconds=record.interval_seconds),
            )
    record.updated_at = utc_now()
    session.commit()
    return record


def list_subscriptions(session: Session, *, limit: int = 200) -> list[dict]:
    rows = session.scalars(
        select(SourceSubscriptionRecord)
        .order_by(SourceSubscriptionRecord.created_at.desc())
        .limit(limit)
    ).all()
    return [subscription_to_dict(item) for item in rows]


def list_scan_runs(session: Session, subscription_id: str, *, limit: int = 100) -> list[dict]:
    if get_subscription(session, subscription_id) is None:
        raise ValueError("source subscription not found")
    rows = session.scalars(
        select(SourceScanRunRecord)
        .where(SourceScanRunRecord.subscription_id == subscription_id)
        .order_by(SourceScanRunRecord.started_at.desc())
        .limit(limit)
    ).all()
    return [scan_run_to_dict(item) for item in rows]


def pause_subscription(
    session: Session,
    subscription_id: str,
    *,
    reason: str = "manual",
) -> SourceSubscriptionRecord:
    record = get_subscription(session, subscription_id)
    if record is None:
        raise ValueError("source subscription not found")
    record.status = "paused"
    record.pause_reason = reason
    record.lease_until = None
    record.lease_token = None
    record.updated_at = utc_now()
    session.commit()
    return record


def resume_subscription(session: Session, subscription_id: str) -> SourceSubscriptionRecord:
    record = get_subscription(session, subscription_id)
    if record is None:
        raise ValueError("source subscription not found")
    now = utc_now()
    record.status = "active"
    record.pause_reason = None
    record.consecutive_failures = 0
    record.last_error = None
    record.next_scan_at = now
    record.lease_until = None
    record.lease_token = None
    record.updated_at = now
    session.commit()
    return record


def _lease_expired_clause(now):
    return or_(
        SourceSubscriptionRecord.lease_until.is_(None),
        SourceSubscriptionRecord.lease_until < now,
    )


def claim_due_subscriptions(
    session: Session,
    *,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    settings = get_settings()
    now = utc_now()
    batch_size = limit or settings.source_scan_dispatch_batch_size
    statement = (
        select(SourceSubscriptionRecord)
        .where(
            SourceSubscriptionRecord.status == "active",
            SourceSubscriptionRecord.next_scan_at <= now,
            _lease_expired_clause(now),
        )
        .order_by(SourceSubscriptionRecord.next_scan_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    rows = session.scalars(statement).all()
    lease_until = now + timedelta(seconds=settings.source_scan_lease_seconds)
    claims: list[tuple[str, str]] = []
    for item in rows:
        token = str(uuid4())
        item.lease_until = lease_until
        item.lease_token = token
        item.updated_at = now
        claims.append((item.id, token))
    session.commit()
    return claims


def claim_manual_scan(
    session: Session,
    subscription_id: str,
) -> tuple[SourceSubscriptionRecord, str]:
    settings = get_settings()
    now = utc_now()
    record = _lock_subscription(session, subscription_id)
    if record is None:
        raise ValueError("source subscription not found")
    if record.lease_until is not None and record.lease_until >= now:
        session.rollback()
        raise ValueError("source subscription already has a scan in progress")
    token = str(uuid4())
    record.lease_until = now + timedelta(seconds=settings.source_scan_lease_seconds)
    record.lease_token = token
    record.updated_at = now
    session.commit()
    return record, token


def release_dispatch_claim(
    session: Session,
    subscription_id: str,
    error: str,
    *,
    lease_token: str | None = None,
) -> None:
    settings = get_settings()
    record = _lock_subscription(session, subscription_id)
    if record is None:
        session.rollback()
        return
    if lease_token is not None and record.lease_token != lease_token:
        session.rollback()
        return
    now = utc_now()
    record.lease_until = None
    record.lease_token = None
    record.last_error = f"dispatch failed: {error}"[:2000]
    record.next_scan_at = now + timedelta(seconds=settings.source_scan_dispatch_interval_seconds)
    record.updated_at = now
    session.commit()


def _next_failure_delay(interval_seconds: int, failures: int) -> int:
    settings = get_settings()
    exponent = min(max(failures - 1, 0), 10)
    delay = max(interval_seconds, settings.source_scan_min_interval_seconds) * (2**exponent)
    return min(delay, settings.source_scan_max_backoff_seconds)


def _record_run(
    session: Session,
    *,
    subscription_id: str,
    outcome: str,
    fetch_id: str | None,
    manual: bool,
    not_modified: bool,
    documents_seen: int,
    documents_created: int,
    error_detail: str | None,
    started_at,
    finished_at,
) -> None:
    session.add(
        SourceScanRunRecord(
            id=str(uuid4()),
            subscription_id=subscription_id,
            outcome=outcome,
            fetch_id=fetch_id,
            manual=manual,
            not_modified=not_modified,
            documents_seen=documents_seen,
            documents_created=documents_created,
            error_detail=error_detail,
            started_at=started_at,
            finished_at=finished_at,
        )
    )


def _scan_snapshot(record: SourceSubscriptionRecord, *, outcome: str) -> SourceScanResult:
    return SourceScanResult(
        subscription_id=record.id,
        outcome=outcome,
        consecutive_failures=record.consecutive_failures,
        next_scan_at=record.next_scan_at.isoformat(),
        status=record.status,
    )


async def scan_subscription(
    session: Session,
    subscription_id: str,
    *,
    manual: bool = False,
    lease_token: str | None = None,
    store: DocumentStore | None = None,
) -> SourceScanResult:
    settings = get_settings()
    started_at = utc_now()
    record = get_subscription(session, subscription_id)
    if record is None:
        raise ValueError("source subscription not found")
    if lease_token is not None and record.lease_token != lease_token:
        return _scan_snapshot(record, outcome="stale_claim")
    if not manual and record.status != "active":
        if lease_token is None or record.lease_token == lease_token:
            record.lease_until = None
            record.lease_token = None
            session.commit()
        return _scan_snapshot(record, outcome="skipped")

    try:
        outcome = await fetch_documents_conditional(
            record.connector,
            record.url,
            if_none_match=record.etag,
            if_modified_since=record.last_modified,
        )

        # Do not keep a database row lock while doing network I/O. Re-lock after the fetch
        # and fence the result with the durable token so an expired/stale task cannot overwrite
        # a newer worker's state.
        record = _lock_subscription(session, subscription_id)
        if record is None:
            session.rollback()
            raise ValueError("source subscription disappeared during scan")
        if lease_token is not None and record.lease_token != lease_token:
            session.rollback()
            return _scan_snapshot(record, outcome="stale_claim")
        if not manual and record.status != "active":
            record.lease_until = None
            record.lease_token = None
            session.commit()
            return _scan_snapshot(record, outcome="skipped")

        archive = None
        changed = False
        if not outcome.not_modified:
            if outcome.result is None:
                raise RuntimeError("connector returned no result for modified response")
            archive = archive_connector_result(
                outcome.result,
                session,
                store=store,
                commit=False,
            )
            changed = archive.fetch_created

        finished_at = utc_now()
        if outcome.not_modified:
            record.etag = outcome.etag or record.etag
            record.last_modified = outcome.last_modified or record.last_modified
        else:
            record.etag = outcome.etag
            record.last_modified = outcome.last_modified
        record.consecutive_failures = 0
        record.total_scans += 1
        record.last_scan_at = finished_at
        record.last_success_at = finished_at
        record.last_error = None
        record.lease_until = None
        record.lease_token = None
        record.next_scan_at = finished_at + timedelta(seconds=record.interval_seconds)
        if outcome.not_modified:
            result_outcome = "not_modified"
        elif changed:
            result_outcome = "changed"
            record.total_changes += 1
            record.last_changed_at = finished_at
        else:
            result_outcome = "unchanged"
        record.last_outcome = result_outcome
        record.updated_at = finished_at

        fetch_id = archive.fetch_id if archive else None
        documents_seen = archive.documents_seen if archive else 0
        documents_created = archive.documents_created if archive else 0
        _record_run(
            session,
            subscription_id=record.id,
            outcome=result_outcome,
            fetch_id=fetch_id,
            manual=manual,
            not_modified=outcome.not_modified,
            documents_seen=documents_seen,
            documents_created=documents_created,
            error_detail=None,
            started_at=started_at,
            finished_at=finished_at,
        )
        session.commit()
        return SourceScanResult(
            subscription_id=record.id,
            outcome=result_outcome,
            changed=changed,
            not_modified=outcome.not_modified,
            fetch_id=fetch_id,
            documents_seen=documents_seen,
            documents_created=documents_created,
            consecutive_failures=0,
            next_scan_at=record.next_scan_at.isoformat(),
            status=record.status,
        )
    except Exception as exc:
        session.rollback()
        finished_at = utc_now()
        record = _lock_subscription(session, subscription_id)
        if record is None:
            session.rollback()
            raise
        if lease_token is not None and record.lease_token != lease_token:
            session.rollback()
            return _scan_snapshot(record, outcome="stale_claim")
        error = f"{type(exc).__name__}: {exc}"[:2000]
        record.consecutive_failures += 1
        record.total_scans += 1
        record.last_scan_at = finished_at
        record.last_outcome = "failed"
        record.last_error = error
        record.lease_until = None
        record.lease_token = None
        record.next_scan_at = finished_at + timedelta(
            seconds=_next_failure_delay(record.interval_seconds, record.consecutive_failures)
        )
        if record.consecutive_failures >= settings.source_scan_auto_pause_failures:
            record.status = "paused"
            record.pause_reason = "automatic_failure_threshold"
        record.updated_at = finished_at
        _record_run(
            session,
            subscription_id=record.id,
            outcome="failed",
            fetch_id=None,
            manual=manual,
            not_modified=False,
            documents_seen=0,
            documents_created=0,
            error_detail=error,
            started_at=started_at,
            finished_at=finished_at,
        )
        session.commit()
        return SourceScanResult(
            subscription_id=record.id,
            outcome="failed",
            consecutive_failures=record.consecutive_failures,
            next_scan_at=record.next_scan_at.isoformat(),
            status=record.status,
            error=error,
        )

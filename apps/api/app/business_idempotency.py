import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .db import IdempotencyRecord

SAFE_KEY = re.compile(r"^[!-~]{8,200}$")


@dataclass(frozen=True)
class IdempotencyHandle:
    record_id: int | None
    replay_payload: dict | None = None
    replay_status: int | None = None

    @property
    def is_replay(self) -> bool:
        return self.replay_payload is not None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _key_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_key(raw_key: str | None) -> str | None:
    settings = get_settings()
    if raw_key is None or not raw_key.strip():
        if settings.app_env == "production":
            raise HTTPException(
                status_code=428,
                detail="Idempotency-Key is required for this production write operation",
            )
        return None
    normalized = raw_key.strip()
    if not SAFE_KEY.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key must be 8-200 printable ASCII characters without spaces",
        )
    return normalized


def _interpret_existing(record: IdempotencyRecord, request_hash: str) -> IdempotencyHandle:
    if record.request_hash != request_hash:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key was already used with a different request payload",
        )
    if record.status == "completed" and record.response_payload is not None:
        return IdempotencyHandle(
            record_id=record.id,
            replay_payload=record.response_payload,
            replay_status=record.response_status or 200,
        )
    if record.status == "failed":
        raise HTTPException(
            status_code=409,
            detail="Previous attempt with this Idempotency-Key failed or has uncertain side effects; use a new key after review",
        )
    raise HTTPException(
        status_code=409,
        detail="An operation with this Idempotency-Key is already in progress",
    )


def begin_operation(
    session: Session,
    *,
    organization_id: str,
    scope: str,
    raw_key: str | None,
    request_payload: Any,
) -> IdempotencyHandle:
    key = _validate_key(raw_key)
    if key is None:
        return IdempotencyHandle(record_id=None)

    key_digest = _key_hash(key)
    request_digest = _canonical_hash(request_payload)
    now = _now()

    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == organization_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == key_digest,
        )
    )
    if existing is not None:
        if existing.expires_at <= now:
            session.delete(existing)
            session.commit()
        else:
            return _interpret_existing(existing, request_digest)

    record = IdempotencyRecord(
        organization_id=organization_id,
        key_hash=key_digest,
        scope=scope,
        request_hash=request_digest,
        status="pending",
        expires_at=now + timedelta(seconds=get_settings().idempotency_ttl_seconds),
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        winner = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.organization_id == organization_id,
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.key_hash == key_digest,
            )
        )
        if winner is None:
            raise
        return _interpret_existing(winner, request_digest)
    return IdempotencyHandle(record_id=record.id)


def complete_operation(
    session: Session,
    handle: IdempotencyHandle,
    response_payload: dict,
    *,
    response_status: int = 200,
) -> None:
    if handle.record_id is None:
        return
    record = session.get(IdempotencyRecord, handle.record_id)
    if record is None:
        raise RuntimeError("Idempotency record disappeared before completion")
    record.status = "completed"
    record.response_status = response_status
    record.response_payload = response_payload
    record.error_detail = None
    session.commit()


def fail_operation(session: Session, handle: IdempotencyHandle, detail: str) -> None:
    if handle.record_id is None:
        return
    # The business operation may have left the Session in a failed transaction state.
    # Roll back uncommitted work before persisting the conservative failed marker.
    session.rollback()
    record = session.get(IdempotencyRecord, handle.record_id)
    if record is None:
        return
    record.status = "failed"
    record.error_detail = detail[:2000]
    session.commit()

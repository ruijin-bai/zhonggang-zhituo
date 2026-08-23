import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

import redis
from celery.result import AsyncResult

from .celery_app import celery_app
from .config import get_settings
from .security import Principal

settings = get_settings()
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
JOB_META_PREFIX = "zhituo:job:"
IDEMPOTENCY_PREFIX = "zhituo:idempotency:"


def _key(job_id: str) -> str:
    return f"{JOB_META_PREFIX}{job_id}"


def _idempotency_key(organization_id: str, job_type: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"{IDEMPOTENCY_PREFIX}{organization_id}:{job_type}:{digest}"


def validate_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not 8 <= len(normalized) <= 200:
        raise ValueError("Idempotency-Key must contain 8 to 200 characters")
    if any(ord(char) < 33 or ord(char) > 126 for char in normalized):
        raise ValueError("Idempotency-Key must use printable ASCII without spaces")
    return normalized


def reserve_job_id(
    *,
    principal: Principal,
    job_type: str,
    idempotency_key: str | None,
) -> tuple[str, bool]:
    """Return (job_id, replayed). Redis SET NX makes concurrent retries converge."""
    normalized = validate_idempotency_key(idempotency_key)
    if normalized is None:
        return str(uuid4()), False

    redis_key = _idempotency_key(principal.organization_id, job_type, normalized)
    candidate = str(uuid4())
    created = redis_client.set(
        redis_key,
        candidate,
        nx=True,
        ex=settings.idempotency_ttl_seconds,
    )
    if created:
        return candidate, False
    existing = redis_client.get(redis_key)
    if not existing:
        # The key may have expired between SET NX and GET; retry exactly once.
        created = redis_client.set(
            redis_key,
            candidate,
            nx=True,
            ex=settings.idempotency_ttl_seconds,
        )
        if created:
            return candidate, False
        existing = redis_client.get(redis_key)
    if not existing:
        raise RuntimeError("Unable to resolve idempotent job reservation")
    return existing, True


def release_job_reservation(
    *,
    principal: Principal,
    job_type: str,
    idempotency_key: str | None,
    job_id: str,
) -> None:
    normalized = validate_idempotency_key(idempotency_key)
    if normalized is None:
        return
    redis_key = _idempotency_key(principal.organization_id, job_type, normalized)
    # Compare-and-delete prevents deleting another request's reservation after a race.
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """
    redis_client.eval(script, 1, redis_key, job_id)


def register_job(
    job_id: str,
    *,
    principal: Principal,
    job_type: str,
    resource_id: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
) -> None:
    payload = {
        "job_id": job_id,
        "job_type": job_type,
        "organization_id": principal.organization_id,
        "submitted_by": principal.user_id,
        "submitted_by_email": principal.email,
        "resource_id": resource_id,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "idempotency_key_present": bool(idempotency_key),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    redis_client.setex(
        _key(job_id),
        settings.celery_result_expires_seconds,
        json.dumps(payload, ensure_ascii=False),
    )


def job_metadata(job_id: str, principal: Principal) -> dict:
    raw = redis_client.get(_key(job_id))
    if raw is None:
        raise ValueError("Job not found or expired")
    payload = json.loads(raw)
    if payload.get("organization_id") != principal.organization_id:
        raise PermissionError("Job belongs to another organization")
    return payload


def job_snapshot(job_id: str, principal: Principal) -> dict:
    meta = job_metadata(job_id, principal)
    result = AsyncResult(job_id, app=celery_app)
    payload = {
        **meta,
        "state": result.state,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
        "result": None,
        "error": None,
    }
    if result.successful():
        payload["result"] = result.result
    elif result.failed():
        payload["error"] = str(result.result)
    return payload

import json
from datetime import datetime, timezone

import redis
from celery.result import AsyncResult

from .celery_app import celery_app
from .config import get_settings
from .security import Principal

settings = get_settings()
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
JOB_META_PREFIX = "zhituo:job:"


def _key(job_id: str) -> str:
    return f"{JOB_META_PREFIX}{job_id}"


def register_job(job_id: str, *, principal: Principal, job_type: str, resource_id: str | None = None) -> None:
    payload = {
        "job_id": job_id,
        "job_type": job_type,
        "organization_id": principal.organization_id,
        "submitted_by": principal.user_id,
        "submitted_by_email": principal.email,
        "resource_id": resource_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    redis_client.setex(_key(job_id), settings.celery_result_expires_seconds, json.dumps(payload, ensure_ascii=False))


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

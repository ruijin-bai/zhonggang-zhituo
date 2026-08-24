import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import BackgroundJobRecord, SessionLocal, set_tenant_context
from .security import Principal

logger = logging.getLogger("zhituo.jobs")
TERMINAL_JOB_STATES = {"succeeded", "failed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job_record(
    session: Session,
    *,
    job_id: str,
    principal: Principal,
    job_type: str,
    task_name: str,
    task_args: list,
    resource_id: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    retry_of_job_id: str | None = None,
) -> BackgroundJobRecord:
    record = BackgroundJobRecord(
        id=job_id,
        job_type=job_type,
        task_name=task_name,
        task_args=task_args,
        resource_id=resource_id,
        submitted_by_user_id=principal.user_id,
        submitted_by_email=principal.email,
        status="queued",
        attempts=0,
        retry_of_job_id=retry_of_job_id,
        request_id=request_id,
        correlation_id=correlation_id,
        error_detail=None,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def transition_job_record(
    session: Session,
    job_id: str,
    *,
    status: str,
    error_detail: str | None = None,
    increment_attempt: bool = False,
) -> BackgroundJobRecord | None:
    record = session.get(BackgroundJobRecord, job_id)
    if record is None:
        return None

    now = _now()
    record.status = status
    if increment_attempt:
        record.attempts += 1
        if record.started_at is None:
            record.started_at = now
    if status == "running" and record.started_at is None:
        record.started_at = now
    if status in TERMINAL_JOB_STATES:
        record.finished_at = now
    elif status in {"queued", "retrying", "running"}:
        record.finished_at = None
    record.error_detail = error_detail[:4000] if error_detail else None
    record.updated_at = now
    session.commit()
    session.refresh(record)
    return record


def transition_job_runtime(
    *,
    organization_id: str,
    job_id: str,
    status: str,
    error_detail: str | None = None,
    increment_attempt: bool = False,
) -> None:
    """Best-effort Worker-side transition that never masks the actual Celery result."""
    try:
        with SessionLocal() as session:
            set_tenant_context(session, organization_id)
            transition_job_record(
                session,
                job_id,
                status=status,
                error_detail=error_detail,
                increment_attempt=increment_attempt,
            )
    except Exception:
        logger.exception(
            "background job ledger transition failed",
            extra={"job_id": job_id, "organization_id": organization_id, "status": status},
        )


def get_job_record(session: Session, job_id: str) -> BackgroundJobRecord | None:
    return session.get(BackgroundJobRecord, job_id)


def list_failed_job_records(session: Session, *, limit: int = 100) -> list[BackgroundJobRecord]:
    return session.scalars(
        select(BackgroundJobRecord)
        .where(BackgroundJobRecord.status == "failed")
        .order_by(BackgroundJobRecord.finished_at.desc(), BackgroundJobRecord.submitted_at.desc())
        .limit(limit)
    ).all()


def record_to_dict(record: BackgroundJobRecord) -> dict:
    return {
        "job_id": record.id,
        "job_type": record.job_type,
        "task_name": record.task_name,
        "resource_id": record.resource_id,
        "status": record.status,
        "attempts": record.attempts,
        "retry_of_job_id": record.retry_of_job_id,
        "submitted_by_email": record.submitted_by_email,
        "request_id": record.request_id,
        "correlation_id": record.correlation_id,
        "error": record.error_detail,
        "submitted_at": record.submitted_at.isoformat() if record.submitted_at else None,
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
    }

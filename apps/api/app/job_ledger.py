import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import BackgroundJobRecord, SessionLocal, set_tenant_context
from .metrics import observe_job_transition, observe_stuck_reconciled
from .security import Principal

logger = logging.getLogger("zhituo.jobs")
TERMINAL_JOB_STATES = {"succeeded", "failed"}
ACTIVE_JOB_STATES = {"queued", "running", "retrying"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
    observe_job_transition(job_type, "queued")
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
    elif status in ACTIVE_JOB_STATES:
        record.finished_at = None
    record.error_detail = error_detail[:4000] if error_detail else None
    record.updated_at = now
    session.commit()
    session.refresh(record)
    observe_job_transition(record.job_type, status, increment_attempt=increment_attempt)
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


def list_stuck_job_records(
    session: Session,
    *,
    threshold_seconds: int | None = None,
    limit: int = 500,
) -> list[BackgroundJobRecord]:
    threshold = threshold_seconds or get_settings().job_stuck_after_seconds
    cutoff = _now() - timedelta(seconds=threshold)
    return session.scalars(
        select(BackgroundJobRecord)
        .where(
            BackgroundJobRecord.status.in_(ACTIVE_JOB_STATES),
            BackgroundJobRecord.updated_at < cutoff,
        )
        .order_by(BackgroundJobRecord.updated_at.asc())
        .limit(limit)
    ).all()


def reconcile_stuck_jobs(
    session: Session,
    *,
    threshold_seconds: int | None = None,
) -> list[str]:
    now = _now()
    threshold = threshold_seconds or get_settings().job_stuck_after_seconds
    reconciled: list[str] = []
    for record in list_stuck_job_records(
        session,
        threshold_seconds=threshold,
    ):
        last_seen = _as_utc(record.updated_at)
        age_seconds = max(0, int((now - last_seen).total_seconds()))
        record.status = "failed"
        record.finished_at = now
        record.updated_at = now
        record.error_detail = (
            f"stuck-job reconciler marked task failed after {age_seconds}s without state update; "
            f"threshold={threshold}s"
        )
        reconciled.append(record.id)
        observe_job_transition(record.job_type, "failed")
        observe_stuck_reconciled(record.job_type)
        logger.warning(
            "background job reconciled as stuck",
            extra={
                "event": "job.stuck.reconciled",
                "job_id": record.id,
                "job_type": record.job_type,
                "organization_id": record.organization_id,
            },
        )
    if reconciled:
        session.commit()
    return reconciled


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

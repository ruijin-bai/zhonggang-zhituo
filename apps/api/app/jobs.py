from collections.abc import Sequence

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .audit import write_audit
from .db import get_db
from .job_ledger import (
    create_job_record,
    get_job_record,
    list_failed_job_records,
    record_to_dict,
    transition_job_record,
)
from .job_registry import (
    job_snapshot,
    register_job,
    release_job_reservation,
    reserve_job_id,
)
from .models import DiscoverRequest, SourceIngestRequest
from .radar import BatchScanRequest
from .security import Principal, require_role
from .tasks import (
    discovery_batch_task,
    discovery_scan_task,
    opportunity_analyze_task,
    source_ingest_task,
    strategy_generate_task,
    strategy_red_team_task,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

RETRYABLE_TASKS = {
    task.name: task
    for task in (
        discovery_scan_task,
        discovery_batch_task,
        source_ingest_task,
        opportunity_analyze_task,
        strategy_generate_task,
        strategy_red_team_task,
    )
}


class JobSubmission(BaseModel):
    job_id: str
    job_type: str
    state: str = "PENDING"
    status_url: str
    replayed: bool = False


def _request_context(request: Request) -> tuple[str | None, str | None]:
    return (
        getattr(request.state, "request_id", None),
        getattr(request.state, "correlation_id", None),
    )


def _enqueue(
    task,
    *,
    args: Sequence,
    job_type: str,
    principal: Principal,
    request: Request,
    db: Session,
    idempotency_key: str | None,
    resource_id: str | None = None,
    retry_of_job_id: str | None = None,
) -> JobSubmission:
    try:
        job_id, replayed = reserve_job_id(
            principal=principal,
            job_type=job_type,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request_id, correlation_id = _request_context(request)
    if replayed:
        return JobSubmission(
            job_id=job_id,
            job_type=job_type,
            status_url=f"/api/jobs/{job_id}",
            replayed=True,
        )

    create_job_record(
        db,
        job_id=job_id,
        principal=principal,
        job_type=job_type,
        task_name=task.name,
        task_args=list(args),
        resource_id=resource_id,
        request_id=request_id,
        correlation_id=correlation_id,
        retry_of_job_id=retry_of_job_id,
    )

    try:
        register_job(
            job_id,
            principal=principal,
            job_type=job_type,
            resource_id=resource_id,
            request_id=request_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        task.apply_async(
            args=list(args),
            task_id=job_id,
            headers={
                "request_id": request_id,
                "correlation_id": correlation_id,
                "organization_id": principal.organization_id,
            },
        )
    except Exception as exc:
        transition_job_record(db, job_id, status="failed", error_detail=f"dispatch failed: {exc}")
        release_job_reservation(
            principal=principal,
            job_type=job_type,
            idempotency_key=idempotency_key,
            job_id=job_id,
        )
        raise

    return JobSubmission(
        job_id=job_id,
        job_type=job_type,
        status_url=f"/api/jobs/{job_id}",
        replayed=False,
    )


def _audit_submission(
    db: Session,
    request: Request,
    principal: Principal,
    result: JobSubmission,
    details: dict | None = None,
) -> None:
    write_audit(
        db,
        principal=principal,
        action="job.replay" if result.replayed else "job.submit",
        resource_type="job",
        resource_id=result.job_id,
        request=request,
        details={"job_type": result.job_type, "replayed": result.replayed, **(details or {})},
    )
    db.commit()


@router.post("/discovery/scan", response_model=JobSubmission, status_code=202)
def submit_discovery_scan(
    body: DiscoverRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobSubmission:
    result = _enqueue(
        discovery_scan_task,
        args=(body.model_dump(mode="json"), principal.organization_id),
        job_type="discovery.scan",
        principal=principal,
        request=request,
        db=db,
        idempotency_key=idempotency_key,
    )
    _audit_submission(db, request, principal, result)
    return result


@router.post("/discovery/batch", response_model=JobSubmission, status_code=202)
def submit_discovery_batch(
    body: BatchScanRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobSubmission:
    result = _enqueue(
        discovery_batch_task,
        args=(body.model_dump(mode="json"), principal.organization_id),
        job_type="discovery.batch",
        principal=principal,
        request=request,
        db=db,
        idempotency_key=idempotency_key,
    )
    _audit_submission(db, request, principal, result, {"items": len(body.items)})
    return result


@router.post("/sources/ingest", response_model=JobSubmission, status_code=202)
def submit_source_ingest(
    body: SourceIngestRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobSubmission:
    result = _enqueue(
        source_ingest_task,
        args=(body.model_dump(mode="json"), principal.organization_id),
        job_type="source.ingest",
        principal=principal,
        request=request,
        db=db,
        idempotency_key=idempotency_key,
        resource_id=body.opportunity_id,
    )
    _audit_submission(db, request, principal, result, {"opportunity_id": body.opportunity_id})
    return result


@router.post("/opportunities/{opportunity_id}/analyze", response_model=JobSubmission, status_code=202)
def submit_analysis(
    opportunity_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobSubmission:
    result = _enqueue(
        opportunity_analyze_task,
        args=(opportunity_id, principal.organization_id),
        job_type="opportunity.analyze",
        principal=principal,
        request=request,
        db=db,
        idempotency_key=idempotency_key,
        resource_id=opportunity_id,
    )
    _audit_submission(db, request, principal, result, {"opportunity_id": opportunity_id})
    return result


@router.post("/opportunities/{opportunity_id}/strategy/generate", response_model=JobSubmission, status_code=202)
def submit_strategy_generate(
    opportunity_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobSubmission:
    result = _enqueue(
        strategy_generate_task,
        args=(opportunity_id, principal.organization_id),
        job_type="strategy.generate",
        principal=principal,
        request=request,
        db=db,
        idempotency_key=idempotency_key,
        resource_id=opportunity_id,
    )
    _audit_submission(db, request, principal, result, {"opportunity_id": opportunity_id})
    return result


@router.post("/opportunities/{opportunity_id}/strategy/red-team", response_model=JobSubmission, status_code=202)
def submit_strategy_red_team(
    opportunity_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobSubmission:
    result = _enqueue(
        strategy_red_team_task,
        args=(opportunity_id, principal.organization_id),
        job_type="strategy.red_team",
        principal=principal,
        request=request,
        db=db,
        idempotency_key=idempotency_key,
        resource_id=opportunity_id,
    )
    _audit_submission(db, request, principal, result, {"opportunity_id": opportunity_id})
    return result


@router.get("/failed")
def failed_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> list[dict]:
    return [record_to_dict(item) for item in list_failed_job_records(db, limit=limit)]


@router.post("/{job_id}/retry", response_model=JobSubmission, status_code=202)
def retry_failed_job(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> JobSubmission:
    record = get_job_record(db, job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed jobs can be retried manually")
    task = RETRYABLE_TASKS.get(record.task_name)
    if task is None:
        raise HTTPException(status_code=409, detail="This job type is not approved for manual retry")

    result = _enqueue(
        task,
        args=record.task_args,
        job_type=record.job_type,
        principal=principal,
        request=request,
        db=db,
        idempotency_key=None,
        resource_id=record.resource_id,
        retry_of_job_id=record.id,
    )
    _audit_submission(
        db,
        request,
        principal,
        result,
        {"retry_of_job_id": record.id, "manual_retry": True},
    )
    return result


@router.get("/{job_id}")
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> dict:
    durable = get_job_record(db, job_id)
    try:
        payload = job_snapshot(job_id, principal)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError:
        if durable is None:
            raise HTTPException(status_code=404, detail="Job not found or expired")
        ledger = record_to_dict(durable)
        return {
            **ledger,
            "state": durable.status.upper(),
            "ready": durable.status in {"succeeded", "failed"},
            "successful": durable.status == "succeeded" if durable.status in {"succeeded", "failed"} else None,
            "result": None,
        }

    if durable is not None:
        ledger = record_to_dict(durable)
        payload["ledger"] = ledger
        # Dispatch failures or expired Celery result state must not hide the durable failure fact.
        if durable.status == "failed" and not payload.get("ready"):
            payload.update(
                state="FAILURE",
                ready=True,
                successful=False,
                error=durable.error_detail,
            )
    return payload

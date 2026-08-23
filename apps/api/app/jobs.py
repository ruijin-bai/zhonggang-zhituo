from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .audit import write_audit
from .db import get_db
from .job_registry import job_snapshot, register_job
from .models import DiscoverRequest, SourceIngestRequest
from .radar import BatchScanRequest
from .security import Principal, require_role
from .tasks import discovery_batch_task, discovery_scan_task, opportunity_analyze_task, source_ingest_task

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobSubmission(BaseModel):
    job_id: str
    job_type: str
    state: str = "PENDING"
    status_url: str


def _submitted(task, *, job_type: str, principal: Principal, resource_id: str | None = None) -> JobSubmission:
    register_job(task.id, principal=principal, job_type=job_type, resource_id=resource_id)
    return JobSubmission(job_id=task.id, job_type=job_type, status_url=f"/api/jobs/{task.id}")


@router.post("/discovery/scan", response_model=JobSubmission, status_code=202)
def submit_discovery_scan(
    body: DiscoverRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> JobSubmission:
    task = discovery_scan_task.delay(body.model_dump(mode="json"))
    result = _submitted(task, job_type="discovery.scan", principal=principal)
    write_audit(db, principal=principal, action="job.submit", resource_type="job", resource_id=task.id, request=request, details={"job_type": result.job_type})
    db.commit()
    return result


@router.post("/discovery/batch", response_model=JobSubmission, status_code=202)
def submit_discovery_batch(
    body: BatchScanRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> JobSubmission:
    task = discovery_batch_task.delay(body.model_dump(mode="json"))
    result = _submitted(task, job_type="discovery.batch", principal=principal)
    write_audit(db, principal=principal, action="job.submit", resource_type="job", resource_id=task.id, request=request, details={"job_type": result.job_type, "items": len(body.items)})
    db.commit()
    return result


@router.post("/sources/ingest", response_model=JobSubmission, status_code=202)
def submit_source_ingest(
    body: SourceIngestRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> JobSubmission:
    task = source_ingest_task.delay(body.model_dump(mode="json"))
    result = _submitted(task, job_type="source.ingest", principal=principal, resource_id=body.opportunity_id)
    write_audit(db, principal=principal, action="job.submit", resource_type="job", resource_id=task.id, request=request, details={"job_type": result.job_type, "opportunity_id": body.opportunity_id})
    db.commit()
    return result


@router.post("/opportunities/{opportunity_id}/analyze", response_model=JobSubmission, status_code=202)
def submit_analysis(
    opportunity_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> JobSubmission:
    task = opportunity_analyze_task.delay(opportunity_id)
    result = _submitted(task, job_type="opportunity.analyze", principal=principal, resource_id=opportunity_id)
    write_audit(db, principal=principal, action="job.submit", resource_type="job", resource_id=task.id, request=request, details={"job_type": result.job_type, "opportunity_id": opportunity_id})
    db.commit()
    return result


@router.get("/{job_id}")
def get_job(job_id: str, principal: Principal = Depends(require_role("viewer"))) -> dict:
    try:
        return job_snapshot(job_id, principal)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

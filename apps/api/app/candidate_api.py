from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import write_audit
from .candidate_db import CandidateProcessingRecord
from .candidate_pipeline import list_candidate_processing
from .db import OpportunityDraftRecord, get_db, utc_now
from .models import ProjectDiscovery
from .security import Principal, require_role

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _draft_to_dict(row: OpportunityDraftRecord, processing: CandidateProcessingRecord | None) -> dict:
    discovery = ProjectDiscovery.model_validate(row.discovery)
    return {
        "id": row.id,
        "status": row.status,
        "discovery": discovery.model_dump(mode="json"),
        "source_url": row.source_url,
        "source_title": row.source_title,
        "publisher": row.publisher,
        "published_at": row.published_at,
        "source_rank": row.source_rank,
        "duplicate_matches": row.duplicate_matches or [],
        "source_document_id": processing.source_document_id if processing else None,
        "processing_id": processing.id if processing else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _processing_by_draft(session: Session, draft_ids: list[str]) -> dict[str, CandidateProcessingRecord]:
    if not draft_ids:
        return {}
    rows = session.scalars(
        select(CandidateProcessingRecord).where(CandidateProcessingRecord.draft_id.in_(draft_ids))
    ).all()
    return {row.draft_id: row for row in rows if row.draft_id}


@router.get("")
def candidate_inbox(
    status: str = Query(default="pending", pattern="^(pending|confirmed|rejected|all)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> list[dict]:
    statement = select(OpportunityDraftRecord).order_by(OpportunityDraftRecord.created_at.desc())
    if status != "all":
        statement = statement.where(OpportunityDraftRecord.status == status)
    rows = db.scalars(statement.limit(limit)).all()
    processing = _processing_by_draft(db, [row.id for row in rows])
    return [_draft_to_dict(row, processing.get(row.id)) for row in rows]


@router.get("/processing")
def candidate_processing_queue(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> list[dict]:
    return list_candidate_processing(db, limit=limit)


@router.get("/{draft_id}")
def candidate_detail(
    draft_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> dict:
    row = db.get(OpportunityDraftRecord, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="candidate opportunity not found")
    processing = db.scalar(
        select(CandidateProcessingRecord).where(CandidateProcessingRecord.draft_id == draft_id)
    )
    return _draft_to_dict(row, processing)


@router.post("/{draft_id}/reject")
def reject_candidate(
    draft_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    row = db.get(OpportunityDraftRecord, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="candidate opportunity not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="candidate opportunity has already been reviewed")
    row.status = "rejected"
    row.updated_at = utc_now()
    write_audit(
        db,
        principal=principal,
        action="candidate.reject",
        resource_type="draft",
        resource_id=row.id,
        request=request,
        details={"source_title": row.source_title},
    )
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/processing/{processing_id}/retry")
def retry_candidate_processing(
    processing_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    row = db.get(CandidateProcessingRecord, processing_id)
    if row is None:
        raise HTTPException(status_code=404, detail="candidate processing record not found")
    if row.status in {"processing", "candidate_created"}:
        raise HTTPException(status_code=409, detail="candidate processing is active or already completed")
    now = utc_now()
    row.status = "pending"
    row.attempts = 0
    row.next_attempt_at = now
    row.lease_until = None
    row.lease_token = None
    row.error_detail = None
    row.processed_at = None
    row.updated_at = now
    write_audit(
        db,
        principal=principal,
        action="candidate_processing.retry",
        resource_type="candidate_processing",
        resource_id=row.id,
        request=request,
        details={"source_document_id": row.source_document_id},
    )
    db.commit()
    return {"id": row.id, "status": row.status, "attempts": row.attempts}

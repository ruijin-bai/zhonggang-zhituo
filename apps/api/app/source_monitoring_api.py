from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .audit import write_audit
from .config import get_settings
from .db import get_db
from .security import Principal, require_role
from .source_monitoring import (
    SourceSubscriptionCreate,
    SourceSubscriptionUpdate,
    claim_manual_scan,
    create_subscription,
    get_subscription,
    list_scan_runs,
    list_subscriptions,
    pause_subscription,
    release_dispatch_claim,
    resume_subscription,
    scan_subscription,
    subscription_to_dict,
    update_subscription,
)
from .tasks import source_subscription_scan_task

router = APIRouter(prefix="/api/sources", tags=["sources"])
settings = get_settings()


def _not_found(exc: ValueError) -> HTTPException:
    if "not found" in str(exc).lower():
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _audit(
    db: Session,
    request: Request,
    principal: Principal,
    *,
    action: str,
    subscription_id: str,
    details: dict | None = None,
) -> None:
    write_audit(
        db,
        principal=principal,
        action=action,
        resource_type="source_subscription",
        resource_id=subscription_id,
        request=request,
        details=details or {},
    )
    db.commit()


@router.get("/subscriptions")
def subscriptions(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> list[dict]:
    return list_subscriptions(db, limit=limit)


@router.post("/subscriptions", status_code=201)
def create_source_subscription(
    body: SourceSubscriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    try:
        record = create_subscription(db, body)
    except ValueError as exc:
        raise _not_found(exc) from exc
    _audit(
        db,
        request,
        principal,
        action="source_subscription.create",
        subscription_id=record.id,
        details={"connector": record.connector, "interval_seconds": record.interval_seconds},
    )
    return subscription_to_dict(record)


@router.get("/subscriptions/{subscription_id}")
def source_subscription_detail(
    subscription_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> dict:
    record = get_subscription(db, subscription_id)
    if record is None:
        raise HTTPException(status_code=404, detail="source subscription not found")
    return subscription_to_dict(record)


@router.put("/subscriptions/{subscription_id}")
def update_source_subscription(
    subscription_id: str,
    body: SourceSubscriptionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    try:
        record = update_subscription(db, subscription_id, body)
    except ValueError as exc:
        raise _not_found(exc) from exc
    _audit(
        db,
        request,
        principal,
        action="source_subscription.update",
        subscription_id=record.id,
        details=body.model_dump(exclude_none=True),
    )
    return subscription_to_dict(record)


@router.post("/subscriptions/{subscription_id}/pause")
def pause_source_subscription(
    subscription_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    try:
        record = pause_subscription(db, subscription_id)
    except ValueError as exc:
        raise _not_found(exc) from exc
    _audit(
        db,
        request,
        principal,
        action="source_subscription.pause",
        subscription_id=record.id,
    )
    return subscription_to_dict(record)


@router.post("/subscriptions/{subscription_id}/resume")
def resume_source_subscription(
    subscription_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    try:
        record = resume_subscription(db, subscription_id)
    except ValueError as exc:
        raise _not_found(exc) from exc
    _audit(
        db,
        request,
        principal,
        action="source_subscription.resume",
        subscription_id=record.id,
    )
    return subscription_to_dict(record)


@router.post("/subscriptions/{subscription_id}/scan", status_code=202)
async def scan_source_subscription_now(
    subscription_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    try:
        record = claim_manual_scan(db, subscription_id)
    except ValueError as exc:
        if "in progress" in str(exc).lower():
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise _not_found(exc) from exc

    if settings.job_mode == "inline":
        result = await scan_subscription(db, record.id, manual=True)
        _audit(
            db,
            request,
            principal,
            action="source_subscription.scan.inline",
            subscription_id=record.id,
            details={"outcome": result.outcome},
        )
        return {"mode": "inline", "result": result.model_dump(mode="json")}

    task_id = str(uuid4())
    try:
        source_subscription_scan_task.apply_async(
            args=(record.id, principal.organization_id, True),
            task_id=task_id,
            headers={
                "request_id": getattr(request.state, "request_id", None),
                "correlation_id": getattr(request.state, "correlation_id", None),
                "organization_id": principal.organization_id,
            },
        )
    except Exception as exc:
        release_dispatch_claim(db, record.id, str(exc))
        raise HTTPException(status_code=503, detail="source scan dispatch failed") from exc

    _audit(
        db,
        request,
        principal,
        action="source_subscription.scan.submit",
        subscription_id=record.id,
        details={"task_id": task_id},
    )
    return {"mode": "queue", "task_id": task_id, "subscription_id": record.id}


@router.get("/subscriptions/{subscription_id}/runs")
def source_subscription_runs(
    subscription_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> list[dict]:
    try:
        return list_scan_runs(db, subscription_id, limit=limit)
    except ValueError as exc:
        raise _not_found(exc) from exc

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import AuditLogRecord, get_db
from .security import Principal, get_principal, require_role

router = APIRouter(prefix="/api", tags=["identity"])


class MeResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    organization_id: str
    organization_name: str
    role: str


class AuditItem(BaseModel):
    id: int
    actor_email: str
    action: str
    resource_type: str
    resource_id: str | None
    request_method: str | None
    request_path: str | None
    details: dict
    created_at: datetime


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(get_principal)) -> MeResponse:
    return MeResponse(**principal.__dict__)


@router.get("/admin/audit", response_model=list[AuditItem])
def audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> list[AuditItem]:
    rows = db.scalars(
        select(AuditLogRecord)
        .where(AuditLogRecord.organization_id == principal.organization_id)
        .order_by(AuditLogRecord.created_at.desc())
        .limit(limit)
    ).all()
    return [
        AuditItem(
            id=row.id,
            actor_email=row.actor_email,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            request_method=row.request_method,
            request_path=row.request_path,
            details=row.details or {},
            created_at=row.created_at,
        )
        for row in rows
    ]

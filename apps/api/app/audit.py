from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .db import AuditLogRecord
from .security import Principal


def write_audit(
    session: Session,
    *,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLogRecord:
    record = AuditLogRecord(
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        actor_email=principal.email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_method=request.method if request else None,
        request_path=request.url.path if request else None,
        details=details or {},
    )
    session.add(record)
    return record

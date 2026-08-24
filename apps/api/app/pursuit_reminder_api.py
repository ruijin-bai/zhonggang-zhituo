from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .audit import write_audit
from .business_idempotency import begin_operation, complete_operation, fail_operation
from .db import get_db
from .pursuit_reminders import acknowledge_reminder, reminders_for_member
from .security import Principal, get_principal, require_role

router = APIRouter(prefix="/pursuit", tags=["pursuit-reminders"])


def _key(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key")


@router.get("/reminders")
def pursuit_reminder_inbox(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    try:
        return reminders_for_member(db, principal)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/reminders/{reminder_id}/acknowledge")
def pursuit_reminder_acknowledge(
    reminder_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> dict:
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.reminder.acknowledge:{reminder_id}",
        raw_key=_key(request),
        request_payload={},
    )
    if handle.is_replay:
        return handle.replay_payload

    try:
        row = acknowledge_reminder(
            db,
            reminder_id=reminder_id,
            principal=principal,
        )
        write_audit(
            db,
            principal=principal,
            action="pursuit.reminder.acknowledge",
            resource_type="pursuit_reminder",
            resource_id=row.id,
            request=request,
            details={
                "reminder_type": row.reminder_type,
                "opportunity_id": row.opportunity_id,
                "escalation_level": row.escalation_level,
            },
        )
        db.commit()
        result = {
            "id": row.id,
            "status": row.status,
            "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
        }
        complete_operation(db, handle, result)
        return result
    except PermissionError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise

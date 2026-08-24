from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .audit import write_audit
from .business_idempotency import begin_operation, complete_operation, fail_operation
from .db import get_db, utc_now
from .pursuit_delivery import reminder_delivery_health
from .pursuit_delivery_db import PursuitReminderDeliveryRecord
from .security import Principal, require_role

router = APIRouter(prefix="/pursuit", tags=["pursuit-delivery"])


def _key(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key")


@router.get("/reminder-deliveries")
def pursuit_reminder_delivery_health(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    return reminder_delivery_health(db, limit=limit)


@router.post("/reminder-deliveries/{delivery_id}/retry")
def pursuit_reminder_delivery_retry(
    delivery_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.reminder_delivery.retry:{delivery_id}",
        raw_key=_key(request),
        request_payload={},
    )
    if handle.is_replay:
        return handle.replay_payload

    try:
        row = db.get(PursuitReminderDeliveryRecord, delivery_id)
        if row is None:
            raise ValueError("reminder delivery not found")
        if row.status != "failed":
            raise RuntimeError("only failed reminder deliveries can be manually retried")
        now = utc_now()
        previous_attempt_count = row.attempt_count
        row.status = "retry"
        # Manual retry means an operator has intervened after automatic exhaustion. Give the
        # delivery a fresh automatic retry budget while preserving the previous count in Audit.
        row.attempt_count = 0
        row.next_attempt_at = now
        row.lease_until = None
        row.lease_token = None
        row.error_detail = None
        row.updated_at = now
        write_audit(
            db,
            principal=principal,
            action="pursuit.reminder_delivery.retry",
            resource_type="pursuit_reminder_delivery",
            resource_id=row.id,
            request=request,
            details={
                "reminder_id": row.reminder_id,
                "channel": row.channel,
                "previous_attempt_count": previous_attempt_count,
            },
        )
        db.commit()
        result = {
            "id": row.id,
            "status": row.status,
            "attempt_count": row.attempt_count,
            "next_attempt_at": row.next_attempt_at.isoformat(),
        }
        complete_operation(db, handle, result)
        return result
    except ValueError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise

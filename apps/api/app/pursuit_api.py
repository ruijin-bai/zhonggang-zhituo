from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import write_audit
from .business_idempotency import begin_operation, complete_operation, fail_operation
from .db import MembershipRecord, UserRecord, get_db
from .pursuit_service import (
    add_participant,
    create_work_item,
    emit_pursuit_event,
    ensure_workspace,
    my_work,
    open_gate,
    portfolio,
    record_gate_decision,
    request_gate_review,
    submit_gate_review,
    team_work,
    update_work_item,
    workspace_detail,
)
from .security import Principal, get_principal, require_role

router = APIRouter(prefix="/pursuit", tags=["pursuit"])


class WorkspaceOpen(BaseModel):
    priority: str = Field(default="medium", max_length=20)
    rationale: str = Field(default="", max_length=4000)
    next_review_at: datetime | None = None


class ParticipantUpsert(BaseModel):
    membership_id: int
    participant_role: str = Field(default="contributor", max_length=24)
    responsibility: str = Field(default="", max_length=300)


class WorkItemCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=8000)
    work_type: str = Field(default="action", max_length=24)
    assignee_membership_id: int | None = None
    priority: str = Field(default="medium", max_length=20)
    due_at: datetime | None = None
    dependency_work_item_id: str | None = Field(default=None, max_length=36)


class WorkItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    assignee_membership_id: int | None = None
    clear_assignee: bool = False
    status: str | None = Field(default=None, max_length=24)
    priority: str | None = Field(default=None, max_length=20)
    due_at: datetime | None = None
    clear_due_at: bool = False
    blocked_reason: str | None = Field(default=None, max_length=4000)
    dependency_work_item_id: str | None = Field(default=None, max_length=36)
    clear_dependency: bool = False


class GateCreate(BaseModel):
    gate_type: str = Field(max_length=40)
    title: str = Field(min_length=2, max_length=300)
    due_at: datetime | None = None


class ReviewRequest(BaseModel):
    reviewer_membership_id: int


class ReviewSubmit(BaseModel):
    status: str = Field(max_length=24)
    note: str = Field(default="", max_length=8000)


class DecisionSubmit(BaseModel):
    decision: str = Field(max_length=20)
    rationale: str = Field(min_length=2, max_length=8000)


def _key(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key")


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    raise HTTPException(status_code=409, detail=str(exc)) from exc


def _member_rows(db: Session, principal: Principal) -> list[dict]:
    rows = db.execute(
        select(MembershipRecord, UserRecord)
        .join(UserRecord, UserRecord.id == MembershipRecord.user_id)
        .where(
            MembershipRecord.organization_id == principal.organization_id,
            MembershipRecord.is_active.is_(True),
            UserRecord.is_active.is_(True),
        )
        .order_by(UserRecord.display_name.asc())
    ).all()
    return [
        {
            "membership_id": membership.id,
            "user_id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "role": membership.role,
        }
        for membership, user in rows
    ]


@router.get("/members")
def active_members(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[dict]:
    return _member_rows(db, principal)


@router.get("/my-work")
def pursuit_my_work(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    try:
        return my_work(db, principal)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/team-work")
def pursuit_team_work(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    return team_work(db)


@router.get("/portfolio")
def pursuit_portfolio(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    return portfolio(db)


@router.get("/workspaces/{opportunity_id}")
def pursuit_workspace_detail(
    opportunity_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    try:
        return workspace_detail(db, opportunity_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workspaces/{opportunity_id}/open")
def pursuit_workspace_open(
    opportunity_id: str,
    body: WorkspaceOpen,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    payload = body.model_dump(mode="json")
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.workspace.open:{opportunity_id}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        workspace = ensure_workspace(
            db,
            opportunity_id=opportunity_id,
            principal=principal,
            **body.model_dump(),
        )
        emit_pursuit_event(
            db,
            opportunity_id=opportunity_id,
            event_type="pursuit_workspace_opened",
            payload={"workspace_id": workspace.id, "priority": workspace.priority},
        )
        write_audit(
            db,
            principal=principal,
            action="pursuit.workspace.open",
            resource_type="pursuit_workspace",
            resource_id=workspace.id,
            request=request,
            details={"opportunity_id": opportunity_id},
        )
        db.commit()
        result = workspace_detail(db, opportunity_id)
        complete_operation(db, handle, result)
        return result
    except (ValueError, PermissionError) as exc:
        fail_operation(db, handle, str(exc))
        _raise_service_error(exc)
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@router.post("/workspaces/{workspace_id}/participants")
def pursuit_add_participant(
    workspace_id: str,
    body: ParticipantUpsert,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    payload = body.model_dump(mode="json")
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.participant.upsert:{workspace_id}:{body.membership_id}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        row = add_participant(db, workspace_id=workspace_id, **body.model_dump())
        from .pursuit_db import PursuitWorkspaceRecord
        workspace = db.get(PursuitWorkspaceRecord, workspace_id)
        if workspace is None:
            raise ValueError("pursuit workspace not found")
        emit_pursuit_event(
            db,
            opportunity_id=workspace.opportunity_id,
            event_type="pursuit_participant_updated",
            payload={"membership_id": body.membership_id, "role": body.participant_role},
        )
        write_audit(
            db,
            principal=principal,
            action="pursuit.participant.upsert",
            resource_type="pursuit_workspace",
            resource_id=workspace_id,
            request=request,
            details=payload,
        )
        db.commit()
        result = {"id": row.id, **payload}
        complete_operation(db, handle, result)
        return result
    except (ValueError, PermissionError) as exc:
        fail_operation(db, handle, str(exc))
        _raise_service_error(exc)
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@router.post("/workspaces/{workspace_id}/work-items")
def pursuit_create_work_item(
    workspace_id: str,
    body: WorkItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> dict:
    payload = body.model_dump(mode="json")
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.work_item.create:{workspace_id}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        row = create_work_item(db, workspace_id=workspace_id, principal=principal, **body.model_dump())
        emit_pursuit_event(
            db,
            opportunity_id=row.opportunity_id,
            event_type="pursuit_work_item_created",
            payload={"work_item_id": row.id, "title": row.title},
        )
        write_audit(
            db,
            principal=principal,
            action="pursuit.work_item.create",
            resource_type="pursuit_work_item",
            resource_id=row.id,
            request=request,
            details={"workspace_id": workspace_id, "title": row.title},
        )
        db.commit()
        result = {"id": row.id, "status": row.status, "opportunity_id": row.opportunity_id}
        complete_operation(db, handle, result)
        return result
    except (ValueError, PermissionError) as exc:
        fail_operation(db, handle, str(exc))
        _raise_service_error(exc)
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@router.put("/work-items/{work_item_id}")
def pursuit_update_work_item(
    work_item_id: str,
    body: WorkItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> dict:
    payload = body.model_dump(mode="json", exclude_none=True)
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.work_item.update:{work_item_id}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        row = update_work_item(db, work_item_id=work_item_id, **body.model_dump())
        emit_pursuit_event(
            db,
            opportunity_id=row.opportunity_id,
            event_type="pursuit_work_item_updated",
            payload={"work_item_id": row.id, "status": row.status},
        )
        write_audit(
            db,
            principal=principal,
            action="pursuit.work_item.update",
            resource_type="pursuit_work_item",
            resource_id=row.id,
            request=request,
            details=payload,
        )
        db.commit()
        result = {"id": row.id, "status": row.status, "updated_at": row.updated_at.isoformat()}
        complete_operation(db, handle, result)
        return result
    except (ValueError, PermissionError) as exc:
        fail_operation(db, handle, str(exc))
        _raise_service_error(exc)
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@router.post("/workspaces/{workspace_id}/gates")
def pursuit_open_gate(
    workspace_id: str,
    body: GateCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    payload = body.model_dump(mode="json")
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.gate.open:{workspace_id}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        row = open_gate(db, workspace_id=workspace_id, principal=principal, **body.model_dump())
        emit_pursuit_event(
            db,
            opportunity_id=row.opportunity_id,
            event_type="pursuit_gate_opened",
            payload={"gate_id": row.id, "gate_type": row.gate_type},
        )
        write_audit(
            db,
            principal=principal,
            action="pursuit.gate.open",
            resource_type="pursuit_gate",
            resource_id=row.id,
            request=request,
            details=payload,
        )
        db.commit()
        result = {"id": row.id, "status": row.status, "gate_type": row.gate_type}
        complete_operation(db, handle, result)
        return result
    except (ValueError, PermissionError) as exc:
        fail_operation(db, handle, str(exc))
        _raise_service_error(exc)
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@router.post("/gates/{gate_id}/reviews")
def pursuit_request_review(
    gate_id: str,
    body: ReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    payload = body.model_dump(mode="json")
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.gate.review.request:{gate_id}:{body.reviewer_membership_id}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        row = request_gate_review(
            db,
            gate_id=gate_id,
            reviewer_membership_id=body.reviewer_membership_id,
            principal=principal,
        )
        write_audit(
            db,
            principal=principal,
            action="pursuit.gate.review.request",
            resource_type="pursuit_gate_review",
            resource_id=row.id,
            request=request,
            details=payload,
        )
        db.commit()
        result = {"id": row.id, "status": row.status, "reviewer_membership_id": row.reviewer_membership_id}
        complete_operation(db, handle, result)
        return result
    except (ValueError, PermissionError) as exc:
        fail_operation(db, handle, str(exc))
        _raise_service_error(exc)
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@router.put("/reviews/{review_id}")
def pursuit_submit_review(
    review_id: str,
    body: ReviewSubmit,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> dict:
    payload = body.model_dump(mode="json")
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.gate.review.submit:{review_id}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        row = submit_gate_review(db, review_id=review_id, principal=principal, **body.model_dump())
        write_audit(
            db,
            principal=principal,
            action="pursuit.gate.review.submit",
            resource_type="pursuit_gate_review",
            resource_id=row.id,
            request=request,
            details=payload,
        )
        db.commit()
        result = {"id": row.id, "status": row.status, "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None}
        complete_operation(db, handle, result)
        return result
    except (ValueError, PermissionError) as exc:
        fail_operation(db, handle, str(exc))
        _raise_service_error(exc)
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@router.post("/gates/{gate_id}/decisions")
def pursuit_record_decision(
    gate_id: str,
    body: DecisionSubmit,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    payload = body.model_dump(mode="json")
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"pursuit.gate.decision:{gate_id}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        row = record_gate_decision(db, gate_id=gate_id, principal=principal, **body.model_dump())
        emit_pursuit_event(
            db,
            opportunity_id=row.opportunity_id,
            event_type="pursuit_gate_decided",
            payload={"gate_id": gate_id, "decision_id": row.id, "decision": row.decision},
        )
        write_audit(
            db,
            principal=principal,
            action="pursuit.gate.decision",
            resource_type="pursuit_decision",
            resource_id=row.id,
            request=request,
            details=payload,
        )
        db.commit()
        result = {
            "id": row.id,
            "decision": row.decision,
            "supersedes_decision_id": row.supersedes_decision_id,
            "decided_at": row.decided_at.isoformat(),
        }
        complete_operation(db, handle, result)
        return result
    except (ValueError, PermissionError) as exc:
        fail_operation(db, handle, str(exc))
        _raise_service_error(exc)
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise

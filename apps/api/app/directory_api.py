from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .audit import write_audit
from .business_idempotency import begin_operation, complete_operation, fail_operation
from .db import get_db, utc_now
from .directory_db import DirectoryRoleRuleRecord, DirectorySourceRecord, DirectorySyncRunRecord
from .directory_service import DirectorySnapshot, VALID_ROLES, apply_directory_snapshot, plan_directory_snapshot
from .security import Principal, require_role

router = APIRouter(prefix="/directory", tags=["enterprise-directory"])


class DirectoryRoleRuleInput(BaseModel):
    group: str = Field(min_length=1, max_length=240)
    role: str = Field(max_length=20)

    @field_validator("group")
    @classmethod
    def normalize_group(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized:
            raise ValueError("directory group cannot be blank")
        return normalized

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in VALID_ROLES:
            raise ValueError("unsupported directory role")
        return value


class DirectorySourceUpsert(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=240)
    provider: str = Field(default="snapshot", min_length=2, max_length=40)
    default_role: str = Field(default="viewer", max_length=20)
    authoritative: bool = False
    is_active: bool = True
    role_rules: list[DirectoryRoleRuleInput] = Field(default_factory=list, max_length=200)

    @field_validator("code", "provider")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized

    @field_validator("default_role")
    @classmethod
    def validate_default_role(cls, value: str) -> str:
        if value not in VALID_ROLES:
            raise ValueError("unsupported default role")
        if value == "admin":
            raise ValueError("default directory role cannot be admin; use an explicit group rule")
        return value

    @field_validator("role_rules")
    @classmethod
    def unique_groups(cls, values: list[DirectoryRoleRuleInput]) -> list[DirectoryRoleRuleInput]:
        groups = [value.group for value in values]
        if len(groups) != len(set(groups)):
            raise ValueError("directory role rules contain duplicate groups")
        return values


def _key(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key")


def _source_view(db: Session, source: DirectorySourceRecord) -> dict:
    rules = db.scalars(
        select(DirectoryRoleRuleRecord)
        .where(DirectoryRoleRuleRecord.source_id == source.id)
        .order_by(DirectoryRoleRuleRecord.group_key.asc())
    ).all()
    return {
        "id": source.id,
        "code": source.code,
        "name": source.name,
        "provider": source.provider,
        "default_role": source.default_role,
        "authoritative": source.authoritative,
        "is_active": source.is_active,
        "role_rules": [{"group": row.group_key, "role": row.role} for row in rules],
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat(),
    }


@router.get("/sources")
def directory_sources(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("admin")),
) -> list[dict]:
    rows = db.scalars(select(DirectorySourceRecord).order_by(DirectorySourceRecord.code.asc())).all()
    return [_source_view(db, row) for row in rows]


@router.post("/sources")
def directory_source_upsert(
    body: DirectorySourceUpsert,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("admin")),
) -> dict:
    payload = body.model_dump(mode="json")
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"directory.source.upsert:{body.code}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        source = db.scalar(
            select(DirectorySourceRecord).where(DirectorySourceRecord.code == body.code)
        )
        now = utc_now()
        created = source is None
        if source is None:
            source = DirectorySourceRecord(
                id=str(uuid4()),
                code=body.code,
                name=body.name,
                provider=body.provider,
                default_role=body.default_role,
                authoritative=body.authoritative,
                is_active=body.is_active,
                created_at=now,
                updated_at=now,
            )
            db.add(source)
            db.flush()
        else:
            source.name = body.name
            source.provider = body.provider
            source.default_role = body.default_role
            source.authoritative = body.authoritative
            source.is_active = body.is_active
            source.updated_at = now

        db.execute(
            delete(DirectoryRoleRuleRecord).where(DirectoryRoleRuleRecord.source_id == source.id)
        )
        for rule in body.role_rules:
            db.add(
                DirectoryRoleRuleRecord(
                    source_id=source.id,
                    group_key=rule.group,
                    role=rule.role,
                    created_at=now,
                    updated_at=now,
                )
            )
        write_audit(
            db,
            principal=principal,
            action="directory.source.upsert",
            resource_type="directory_source",
            resource_id=source.id,
            request=request,
            details={
                "code": source.code,
                "provider": source.provider,
                "authoritative": source.authoritative,
                "default_role": source.default_role,
                "role_rule_count": len(body.role_rules),
                "created": created,
            },
        )
        db.commit()
        result = _source_view(db, source)
        complete_operation(db, handle, result)
        return result
    except Exception as exc:
        fail_operation(db, handle, str(exc))
        if isinstance(exc, HTTPException):
            raise
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise


@router.post("/sources/{source_id}/plan")
def directory_snapshot_plan(
    source_id: str,
    body: DirectorySnapshot,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("admin")),
) -> dict:
    try:
        return plan_directory_snapshot(db, source_id=source_id, snapshot=body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sources/{source_id}/sync")
def directory_snapshot_sync(
    source_id: str,
    body: DirectorySnapshot,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("admin")),
) -> dict:
    payload = body.model_dump(mode="json")
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"directory.snapshot.sync:{source_id}",
        raw_key=_key(request),
        request_payload=payload,
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        plan = plan_directory_snapshot(db, source_id=source_id, snapshot=body)
        write_audit(
            db,
            principal=principal,
            action="directory.snapshot.sync",
            resource_type="directory_source",
            resource_id=source_id,
            request=request,
            details={
                "snapshot_sha256": plan["snapshot_sha256"],
                "received_count": plan["received_count"],
                "summary": plan["summary"],
                "authoritative": plan["authoritative"],
            },
        )
        result = apply_directory_snapshot(
            db,
            source_id=source_id,
            snapshot=body,
            principal=principal,
        )
        complete_operation(db, handle, result)
        return result
    except ValueError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@router.get("/sources/{source_id}/runs")
def directory_sync_runs(
    source_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("admin")),
) -> list[dict]:
    source = db.get(DirectorySourceRecord, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="directory source not found")
    rows = db.scalars(
        select(DirectorySyncRunRecord)
        .where(DirectorySyncRunRecord.source_id == source_id)
        .order_by(DirectorySyncRunRecord.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "snapshot_sha256": row.snapshot_sha256,
            "received_count": row.received_count,
            "summary": row.summary or {},
            "actor_user_id": row.actor_user_id,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
        for row in rows
    ]

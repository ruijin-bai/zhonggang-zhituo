from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import write_audit
from .db import OpportunityRecord, get_db
from .entity_management import add_manual_alias
from .intelligence import entity_detail, list_entities
from .security import Principal, require_role

router = APIRouter(prefix="/entities", tags=["entities"])


class AliasCreate(BaseModel):
    alias: str = Field(min_length=2, max_length=320)


@router.get("")
def entity_index(
    q: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> list[dict]:
    return list_entities(db, limit=limit, query=q)


@router.get("/{entity_id}")
def entity_read(
    entity_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> dict:
    result = entity_detail(db, entity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="entity not found")

    opportunity_ids = [item["opportunity_id"] for item in result["opportunities"]]
    opportunities = {}
    if opportunity_ids:
        rows = db.scalars(
            select(OpportunityRecord).where(OpportunityRecord.id.in_(opportunity_ids))
        ).all()
        opportunities = {row.id: row for row in rows}

    for item in result["opportunities"]:
        opportunity = opportunities.get(item["opportunity_id"])
        if opportunity is None:
            item.update({"title": item["opportunity_id"], "country": None, "sector": None, "stage": None})
        else:
            item.update(
                {
                    "title": opportunity.title,
                    "country": opportunity.country,
                    "sector": opportunity.sector,
                    "stage": opportunity.stage,
                }
            )
    return result


@router.post("/{entity_id}/aliases")
def entity_add_alias(
    entity_id: str,
    body: AliasCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> dict:
    try:
        alias = add_manual_alias(db, entity_id=entity_id, alias=body.alias)
        write_audit(
            db,
            principal=principal,
            action="entity.alias.add",
            resource_type="entity",
            resource_id=entity_id,
            request=request,
            details={"alias": alias.alias},
        )
        db.commit()
        return {
            "entity_id": entity_id,
            "alias": alias.alias,
            "normalized_alias": alias.normalized_alias,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

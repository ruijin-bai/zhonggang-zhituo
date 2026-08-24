from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .db import get_db
from .search_knowledge import SEARCH_TYPES, opportunity_knowledge_view, search_knowledge
from .security import Principal, require_role

router = APIRouter(tags=["search"])


def _resource_types(value: str | None) -> set[str] | None:
    if not value:
        return None
    requested = {item.strip() for item in value.split(",") if item.strip()}
    if not requested:
        return None
    unknown = requested - SEARCH_TYPES
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported search types: {', '.join(sorted(unknown))}",
        )
    return requested


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=200),
    types: str | None = Query(
        default=None,
        description="Comma-separated: opportunity,candidate,entity,evidence,source",
    ),
    country: str | None = Query(default=None, min_length=2, max_length=120),
    sector: str | None = Query(default=None, min_length=2, max_length=120),
    entity_role: str | None = Query(
        default=None,
        pattern="^(owner|financier|competitor|partner)$",
    ),
    source_rank: str | None = Query(default=None, pattern="^[SABCD]$"),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> dict:
    del principal
    return search_knowledge(
        db,
        query=q,
        resource_types=_resource_types(types),
        country=country,
        sector=sector,
        entity_role=entity_role,
        source_rank=source_rank,
        limit=limit,
    )


@router.get("/knowledge/opportunities/{opportunity_id}")
def opportunity_knowledge(
    opportunity_id: str,
    related_limit: int = Query(default=20, ge=0, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> dict:
    del principal
    try:
        return opportunity_knowledge_view(
            db,
            opportunity_id,
            related_limit=related_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

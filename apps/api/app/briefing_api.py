from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .briefing import daily_brief
from .db import get_db
from .security import Principal, require_role

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/daily")
def daily_operating_brief(
    window_hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=8, ge=1, le=50),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("viewer")),
) -> dict:
    return daily_brief(db, window_hours=window_hours, limit=limit)

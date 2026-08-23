from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import MembershipRecord, OrganizationRecord, UserRecord, get_db

Role = Literal["viewer", "analyst", "manager", "admin"]
ROLE_LEVEL = {"viewer": 10, "analyst": 20, "manager": 30, "admin": 40}


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    display_name: str
    organization_id: str
    organization_name: str
    role: Role

    def require(self, minimum_role: Role) -> None:
        if ROLE_LEVEL[self.role] < ROLE_LEVEL[minimum_role]:
            raise HTTPException(status_code=403, detail=f"Requires role: {minimum_role}")


def get_principal(
    request: Request,
    db: Session = Depends(get_db),
    x_zhituo_user: str | None = Header(default=None),
) -> Principal:
    settings = get_settings()
    identity = x_zhituo_user or (settings.dev_user_email if settings.app_env != "production" else None)
    if not identity:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = db.scalar(select(UserRecord).where(UserRecord.email == identity, UserRecord.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown or inactive user")

    membership = db.scalar(
        select(MembershipRecord).where(
            MembershipRecord.user_id == user.id,
            MembershipRecord.is_active.is_(True),
        ).order_by(MembershipRecord.created_at.asc())
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="User has no active organization membership")

    organization = db.get(OrganizationRecord, membership.organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=403, detail="Organization is inactive")

    principal = Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=organization.id,
        organization_name=organization.name,
        role=membership.role,
    )
    request.state.principal = principal
    return principal


def require_role(minimum_role: Role):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        principal.require(minimum_role)
        return principal
    return dependency

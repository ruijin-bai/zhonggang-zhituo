from dataclasses import dataclass
from hmac import compare_digest
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


def _resolve_identity(
    *,
    x_zhituo_user: str | None,
    x_zhituo_gateway_secret: str | None,
) -> str:
    settings = get_settings()

    if settings.auth_mode == "trusted_proxy":
        expected = settings.auth_proxy_secret or ""
        supplied = x_zhituo_gateway_secret or ""
        if not expected or not supplied or not compare_digest(expected, supplied):
            raise HTTPException(status_code=401, detail="Request was not authenticated by the trusted identity gateway")
        if not x_zhituo_user:
            raise HTTPException(status_code=401, detail="Trusted identity gateway did not provide a user identity")
        return x_zhituo_user.strip().lower()

    if settings.app_env == "production":
        # Defense in depth: production configuration validation should already reject this,
        # but never allow a direct identity header if a misconfigured process starts.
        raise HTTPException(status_code=503, detail="Production authentication is not configured safely")

    identity = x_zhituo_user or settings.dev_user_email
    if not identity:
        raise HTTPException(status_code=401, detail="Authentication required")
    return identity.strip().lower()


def get_principal(
    request: Request,
    db: Session = Depends(get_db),
    x_zhituo_user: str | None = Header(default=None),
    x_zhituo_gateway_secret: str | None = Header(default=None),
) -> Principal:
    identity = _resolve_identity(
        x_zhituo_user=x_zhituo_user,
        x_zhituo_gateway_secret=x_zhituo_gateway_secret,
    )

    user = db.scalar(
        select(UserRecord).where(
            UserRecord.email == identity,
            UserRecord.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown or inactive user")

    memberships = db.scalars(
        select(MembershipRecord).where(
            MembershipRecord.user_id == user.id,
            MembershipRecord.is_active.is_(True),
        ).order_by(MembershipRecord.created_at.asc())
    ).all()
    if not memberships:
        raise HTTPException(status_code=403, detail="User has no active organization membership")
    if len(memberships) > 1:
        # Until explicit organization selection is implemented, silently choosing one tenant
        # is unsafe. Fail closed rather than risking cross-tenant access.
        raise HTTPException(status_code=409, detail="Multiple organization memberships require explicit organization selection")

    membership = memberships[0]
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

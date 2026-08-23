from dataclasses import dataclass
from functools import lru_cache
from hmac import compare_digest
from typing import Literal

import jwt
from fastapi import Depends, Header, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import MembershipRecord, OrganizationRecord, UserRecord, get_db, set_tenant_context

Role = Literal["viewer", "analyst", "manager", "admin"]
ROLE_LEVEL = {"viewer": 10, "analyst": 20, "manager": 30, "admin": 40}
ALLOWED_JWT_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}


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


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def _oidc_identity(authorization: str | None) -> str:
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")

    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm not in ALLOWED_JWT_ALGORITHMS:
            raise HTTPException(status_code=401, detail="Unsupported JWT signing algorithm")
        signing_key = _jwk_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired OIDC token") from exc

    identity = claims.get(settings.oidc_email_claim)
    if not isinstance(identity, str) or not identity.strip():
        raise HTTPException(status_code=401, detail="OIDC token does not contain a usable identity claim")
    return identity.strip().lower()


def _resolve_identity(
    *,
    authorization: str | None,
    x_zhituo_user: str | None,
    x_zhituo_gateway_secret: str | None,
) -> str:
    settings = get_settings()

    if settings.auth_mode == "oidc":
        return _oidc_identity(authorization)

    if settings.auth_mode == "trusted_proxy":
        expected = settings.auth_proxy_secret or ""
        supplied = x_zhituo_gateway_secret or ""
        if not expected or not supplied or not compare_digest(expected, supplied):
            raise HTTPException(status_code=401, detail="Request was not authenticated by the trusted identity gateway")
        if not x_zhituo_user:
            raise HTTPException(status_code=401, detail="Trusted identity gateway did not provide a user identity")
        return x_zhituo_user.strip().lower()

    if settings.app_env == "production":
        raise HTTPException(status_code=503, detail="Production authentication is not configured safely")

    identity = x_zhituo_user or settings.dev_user_email
    if not identity:
        raise HTTPException(status_code=401, detail="Authentication required")
    return identity.strip().lower()


def _select_membership(
    db: Session,
    user_id: str,
    organization_selector: str | None,
) -> tuple[MembershipRecord, OrganizationRecord]:
    memberships = db.scalars(
        select(MembershipRecord).where(
            MembershipRecord.user_id == user_id,
            MembershipRecord.is_active.is_(True),
        ).order_by(MembershipRecord.created_at.asc())
    ).all()
    if not memberships:
        raise HTTPException(status_code=403, detail="User has no active organization membership")

    if organization_selector:
        selector = organization_selector.strip()
        organization = db.scalar(
            select(OrganizationRecord).where(
                OrganizationRecord.is_active.is_(True),
                or_(OrganizationRecord.id == selector, OrganizationRecord.code == selector),
            )
        )
        if organization is None:
            raise HTTPException(status_code=403, detail="Requested organization is unknown or inactive")
        membership = next(
            (item for item in memberships if item.organization_id == organization.id),
            None,
        )
        if membership is None:
            raise HTTPException(status_code=403, detail="User is not a member of the requested organization")
        return membership, organization

    if len(memberships) > 1:
        raise HTTPException(
            status_code=409,
            detail="Multiple organization memberships require X-Zhituo-Organization",
        )

    membership = memberships[0]
    organization = db.get(OrganizationRecord, membership.organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=403, detail="Organization is inactive")
    return membership, organization


def get_principal(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_zhituo_user: str | None = Header(default=None),
    x_zhituo_gateway_secret: str | None = Header(default=None),
    x_zhituo_organization: str | None = Header(default=None),
) -> Principal:
    identity = _resolve_identity(
        authorization=authorization,
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

    membership, organization = _select_membership(db, user.id, x_zhituo_organization)

    principal = Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=organization.id,
        organization_name=organization.name,
        role=membership.role,
    )
    # Bind both SQLAlchemy ORM filtering and PostgreSQL RLS to this organization.
    set_tenant_context(db, organization.id)
    request.state.principal = principal
    return principal


def require_role(minimum_role: Role):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        principal.require(minimum_role)
        return principal

    return dependency

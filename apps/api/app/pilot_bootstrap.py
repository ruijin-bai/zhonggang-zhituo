from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import MembershipRecord, OrganizationRecord, UserRecord


def ensure_pilot_identity(
    session: Session,
    *,
    email: str,
    display_name: str,
    organization_name: str,
    organization_code: str,
) -> tuple[OrganizationRecord, UserRecord, MembershipRecord]:
    """Create the minimum administrator identity without seeding demo business data."""
    normalized_email = email.strip().casefold()
    normalized_code = organization_code.strip().upper()
    if "@" not in normalized_email or normalized_email.endswith("@zhituo.local"):
        raise ValueError("PILOT_ADMIN_EMAIL must be a non-demo email address")
    if not normalized_code:
        raise ValueError("PILOT_ORGANIZATION_CODE is required")

    organization = session.scalar(
        select(OrganizationRecord).where(OrganizationRecord.code == normalized_code)
    )
    if organization is None:
        organization = OrganizationRecord(
            name=organization_name.strip(),
            code=normalized_code,
            is_active=True,
        )
        session.add(organization)
        session.flush()

    user = session.scalar(select(UserRecord).where(UserRecord.email == normalized_email))
    if user is None:
        user = UserRecord(
            email=normalized_email,
            display_name=display_name.strip(),
            is_active=True,
        )
        session.add(user)
        session.flush()

    membership = session.scalar(
        select(MembershipRecord).where(
            MembershipRecord.organization_id == organization.id,
            MembershipRecord.user_id == user.id,
        )
    )
    if membership is None:
        membership = MembershipRecord(
            organization_id=organization.id,
            user_id=user.id,
            role="admin",
            is_active=True,
        )
        session.add(membership)
    else:
        membership.role = "admin"
        membership.is_active = True

    session.commit()
    return organization, user, membership

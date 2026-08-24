from sqlalchemy import select

from .celery_app import celery_app
from .config import get_settings
from .db import OrganizationRecord, SessionLocal, set_tenant_context
from .pursuit_delivery import (
    claim_reminder_email_deliveries,
    deliver_reminder_email,
    release_reminder_email_dispatch_claim,
    stage_reminder_email_deliveries,
)


@celery_app.task(name="zhituo.pursuit.dispatch_reminder_email")
def dispatch_reminder_email_task() -> dict:
    settings = get_settings()
    if not settings.pursuit_email_delivery_enabled:
        return {
            "enabled": False,
            "organizations_scanned": 0,
            "staged": 0,
            "claimed": 0,
            "dispatched": 0,
            "dispatch_failures": [],
        }

    with SessionLocal() as control_session:
        organization_ids = list(
            control_session.scalars(
                select(OrganizationRecord.id).where(OrganizationRecord.is_active.is_(True))
            ).all()
        )

    staged = 0
    claimed = 0
    dispatched = 0
    dispatch_failures: list[dict] = []
    for organization_id in organization_ids:
        with SessionLocal() as session:
            set_tenant_context(session, organization_id)
            stage_result = stage_reminder_email_deliveries(session, settings=settings)
            staged += int(stage_result["created"])
            claims = claim_reminder_email_deliveries(session, settings=settings)
        claimed += len(claims)

        for delivery_id, lease_token in claims:
            try:
                deliver_reminder_email_task.apply_async(
                    args=(delivery_id, organization_id, lease_token),
                    headers={"organization_id": organization_id},
                )
                dispatched += 1
            except Exception as exc:
                with SessionLocal() as session:
                    set_tenant_context(session, organization_id)
                    release_reminder_email_dispatch_claim(
                        session,
                        delivery_id,
                        str(exc),
                        lease_token=lease_token,
                        settings=settings,
                    )
                dispatch_failures.append(
                    {
                        "organization_id": organization_id,
                        "delivery_id": delivery_id,
                        "error": str(exc)[:500],
                    }
                )

    return {
        "enabled": True,
        "organizations_scanned": len(organization_ids),
        "staged": staged,
        "claimed": claimed,
        "dispatched": dispatched,
        "dispatch_failures": dispatch_failures,
    }


@celery_app.task(name="zhituo.pursuit.deliver_reminder_email")
def deliver_reminder_email_task(
    delivery_id: str,
    organization_id: str,
    lease_token: str,
) -> dict:
    with SessionLocal() as session:
        set_tenant_context(session, organization_id)
        return deliver_reminder_email(
            session,
            delivery_id,
            lease_token=lease_token,
        )

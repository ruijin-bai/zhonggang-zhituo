from sqlalchemy import select

from .celery_app import celery_app
from .db import OrganizationRecord, SessionLocal, set_tenant_context
from .pursuit_reminders import reconcile_pursuit_reminders


@celery_app.task(name="zhituo.pursuit.reconcile_reminders")
def reconcile_pursuit_reminders_task() -> dict:
    with SessionLocal() as control_session:
        organization_ids = list(
            control_session.scalars(
                select(OrganizationRecord.id).where(OrganizationRecord.is_active.is_(True))
            ).all()
        )

    results: list[dict] = []
    for organization_id in organization_ids:
        with SessionLocal() as session:
            set_tenant_context(session, organization_id)
            result = reconcile_pursuit_reminders(session)
            results.append({"organization_id": organization_id, **result})

    return {
        "organizations_scanned": len(organization_ids),
        "results": results,
    }

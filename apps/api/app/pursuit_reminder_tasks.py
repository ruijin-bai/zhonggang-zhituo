from sqlalchemy import select

from .celery_app import celery_app
from .db import OrganizationRecord, SessionLocal, set_tenant_context
from .pursuit_reminders import reconcile_pursuit_reminders


@celery_app.task(
    bind=True,
    name="zhituo.pursuit.reconcile_reminders_for_tenant",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def reconcile_pursuit_reminders_for_tenant_task(self, organization_id: str) -> dict:
    with SessionLocal() as session:
        set_tenant_context(session, organization_id)
        try:
            return {
                "organization_id": organization_id,
                **reconcile_pursuit_reminders(session),
            }
        except Exception as exc:
            session.rollback()
            raise RuntimeError(
                f"pursuit reminder reconciliation failed for organization {organization_id}"
            ) from exc


@celery_app.task(name="zhituo.pursuit.reconcile_reminders")
def reconcile_pursuit_reminders_task() -> dict:
    """Beat dispatcher: isolate reconciliation and dispatch failure per active tenant."""
    with SessionLocal() as control_session:
        organization_ids = list(
            control_session.scalars(
                select(OrganizationRecord.id).where(OrganizationRecord.is_active.is_(True))
            ).all()
        )

    dispatched: list[dict] = []
    dispatch_failures: list[dict] = []
    for organization_id in organization_ids:
        try:
            result = reconcile_pursuit_reminders_for_tenant_task.apply_async(
                args=(organization_id,),
                headers={"organization_id": organization_id},
            )
            dispatched.append(
                {"organization_id": organization_id, "task_id": result.id}
            )
        except Exception as exc:
            dispatch_failures.append(
                {"organization_id": organization_id, "error": str(exc)[:500]}
            )

    return {
        "organizations_scanned": len(organization_ids),
        "dispatched": len(dispatched),
        "tasks": dispatched,
        "dispatch_failures": dispatch_failures,
    }

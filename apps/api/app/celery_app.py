from celery import Celery

from .config import get_settings

settings = get_settings()

celery_app = Celery(
    "zhituo",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks",
        "app.pursuit_reminder_tasks",
        "app.pursuit_delivery_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    result_expires=settings.celery_result_expires_seconds,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    task_time_limit=settings.celery_task_time_limit_seconds,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "reconcile-stuck-background-jobs": {
            "task": "zhituo.maintenance.reconcile_stuck_jobs",
            "schedule": 60.0,
        },
        "dispatch-due-source-scans": {
            "task": "zhituo.sources.dispatch_due_scans",
            "schedule": float(settings.source_scan_dispatch_interval_seconds),
        },
        "dispatch-pending-candidates": {
            "task": "zhituo.candidates.dispatch_pending",
            "schedule": float(settings.candidate_dispatch_interval_seconds),
        },
        "reconcile-pursuit-reminders": {
            "task": "zhituo.pursuit.reconcile_reminders",
            "schedule": float(settings.pursuit_reminder_reconcile_interval_seconds),
        },
        "dispatch-pursuit-reminder-email": {
            "task": "zhituo.pursuit.dispatch_reminder_email",
            "schedule": float(settings.pursuit_email_dispatch_interval_seconds),
        },
    },
)

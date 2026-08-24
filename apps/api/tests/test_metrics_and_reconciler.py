from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base, BackgroundJobRecord, OrganizationRecord, UserRecord, set_tenant_context
from app.job_ledger import count_stale_queued_jobs, reconcile_stuck_jobs


def test_production_metrics_require_dedicated_secret() -> None:
    values = {
        "app_env": "production",
        "data_backend": "database",
        "database_url": "postgresql+psycopg://runtime:secret@db.internal:5432/zhituo",
        "redis_url": "redis://redis.internal:6379/0",
        "demo_mode": False,
        "allow_demo_fallback": False,
        "job_mode": "queue",
        "auth_mode": "trusted_proxy",
        "auth_proxy_secret": "proxy-secret-at-least-32-characters-long",
        "metrics_enabled": True,
    }
    with pytest.raises(ValidationError, match="METRICS_TOKEN"):
        Settings(**values)

    settings = Settings(
        **values,
        metrics_token="metrics-secret-at-least-32-characters-long",
    )
    assert settings.metrics_enabled is True


def test_stuck_job_reconciler_does_not_auto_fail_queued_backlog() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = OrganizationRecord(id=str(uuid4()), name="Ops Org", code="OPS", is_active=True)
        user = UserRecord(
            id=str(uuid4()),
            email="ops@example.com",
            display_name="Ops",
            is_active=True,
        )
        session.add_all([org, user])
        session.commit()
        set_tenant_context(session, org.id)

        stale_running = BackgroundJobRecord(
            id=str(uuid4()),
            job_type="strategy.generate",
            task_name="zhituo.strategy.generate",
            task_args=["opp-1", org.id],
            submitted_by_user_id=user.id,
            submitted_by_email=user.email,
            status="running",
            attempts=1,
            updated_at=datetime.now(timezone.utc) - timedelta(seconds=600),
        )
        stale_queued = BackgroundJobRecord(
            id=str(uuid4()),
            job_type="strategy.generate",
            task_name="zhituo.strategy.generate",
            task_args=["opp-queued", org.id],
            submitted_by_user_id=user.id,
            submitted_by_email=user.email,
            status="queued",
            attempts=0,
            updated_at=datetime.now(timezone.utc) - timedelta(seconds=600),
        )
        recent = BackgroundJobRecord(
            id=str(uuid4()),
            job_type="strategy.generate",
            task_name="zhituo.strategy.generate",
            task_args=["opp-2", org.id],
            submitted_by_user_id=user.id,
            submitted_by_email=user.email,
            status="running",
            attempts=1,
            updated_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
        session.add_all([stale_running, stale_queued, recent])
        session.commit()

        assert count_stale_queued_jobs(session, threshold_seconds=300) == 1
        reconciled = reconcile_stuck_jobs(session, threshold_seconds=300)
        assert reconciled == [stale_running.id]
        assert session.get(BackgroundJobRecord, stale_running.id).status == "failed"
        assert "stuck-job reconciler" in session.get(BackgroundJobRecord, stale_running.id).error_detail
        assert session.get(BackgroundJobRecord, stale_queued.id).status == "queued"
        assert session.get(BackgroundJobRecord, recent.id).status == "running"

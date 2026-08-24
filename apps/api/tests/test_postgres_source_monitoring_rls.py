import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import OrganizationRecord, utc_now
from app.source_db import SourceScanRunRecord, SourceSubscriptionRecord


settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.database_url.startswith("postgresql"),
    reason="PostgreSQL RLS integration test requires PostgreSQL",
)


def _records(*, suffix: str, organization_id: str, marker: str):
    now = utc_now()
    subscription_id = f"sub-{marker}-{suffix}"
    run_id = f"run-{marker}-{suffix}"
    subscription = SourceSubscriptionRecord(
        id=subscription_id,
        organization_id=organization_id,
        name=f"Source {marker}",
        connector="html",
        url=f"https://example.com/{marker}/{suffix}",
        url_hash=(marker * 64)[:64],
        status="active",
        pause_reason=None,
        interval_seconds=3600,
        next_scan_at=now,
        lease_until=None,
        lease_token=None,
        etag=None,
        last_modified=None,
        consecutive_failures=0,
        total_scans=1,
        total_changes=0,
        last_scan_at=now,
        last_success_at=now,
        last_changed_at=None,
        last_outcome="not_modified",
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    run = SourceScanRunRecord(
        id=run_id,
        organization_id=organization_id,
        subscription_id=subscription_id,
        outcome="not_modified",
        fetch_id=None,
        manual=False,
        not_modified=True,
        documents_seen=0,
        documents_created=0,
        error_detail=None,
        started_at=now,
        finished_at=now,
    )
    return subscription, run


def test_postgres_rls_blocks_cross_tenant_subscription_and_run_reads() -> None:
    suffix = uuid.uuid4().hex[:8]
    org_a = f"monitor-rls-org-a-{suffix}"
    org_b = f"monitor-rls-org-b-{suffix}"
    role = f"zhituo_monitor_rls_{suffix}"
    password = f"MonitorRls-{suffix}-Password-123!"
    sub_a, run_a = _records(suffix=suffix, organization_id=org_a, marker="a")
    sub_b, run_b = _records(suffix=suffix, organization_id=org_b, marker="b")
    sub_a_id, sub_b_id = sub_a.id, sub_b.id
    run_a_id, run_b_id = run_a.id, run_b.id

    admin_engine = create_engine(settings.database_url, pool_pre_ping=True)
    runtime_engine = None
    role_created = False
    try:
        with Session(admin_engine) as session:
            session.add_all(
                [
                    OrganizationRecord(
                        id=org_a,
                        name=f"Monitoring RLS Org A {suffix}",
                        code=f"MON-A-{suffix}",
                        is_active=True,
                    ),
                    OrganizationRecord(
                        id=org_b,
                        name=f"Monitoring RLS Org B {suffix}",
                        code=f"MON-B-{suffix}",
                        is_active=True,
                    ),
                ]
            )
            session.flush()
            session.add_all([sub_a, sub_b])
            session.flush()
            session.add_all([run_a, run_b])
            session.commit()

        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\'')
            role_created = True
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            connection.exec_driver_sql(
                f'GRANT SELECT ON TABLE source_subscriptions, source_scan_runs TO "{role}"'
            )

        runtime_url = make_url(settings.database_url).set(username=role, password=password)
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        with runtime_engine.connect() as connection:
            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_a},
            )
            subscription_ids = connection.execute(
                text("SELECT id FROM source_subscriptions WHERE id IN (:a, :b) ORDER BY id"),
                {"a": sub_a_id, "b": sub_b_id},
            ).scalars().all()
            run_ids = connection.execute(
                text("SELECT id FROM source_scan_runs WHERE id IN (:a, :b) ORDER BY id"),
                {"a": run_a_id, "b": run_b_id},
            ).scalars().all()
            assert subscription_ids == [sub_a_id]
            assert run_ids == [run_a_id]

            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_b},
            )
            subscription_ids = connection.execute(
                text("SELECT id FROM source_subscriptions WHERE id IN (:a, :b) ORDER BY id"),
                {"a": sub_a_id, "b": sub_b_id},
            ).scalars().all()
            run_ids = connection.execute(
                text("SELECT id FROM source_scan_runs WHERE id IN (:a, :b) ORDER BY id"),
                {"a": run_a_id, "b": run_b_id},
            ).scalars().all()
            assert subscription_ids == [sub_b_id]
            assert run_ids == [run_b_id]
    finally:
        if runtime_engine is not None:
            runtime_engine.dispose()
        with admin_engine.begin() as connection:
            if role_created:
                connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            connection.execute(
                text("DELETE FROM source_scan_runs WHERE id IN (:a, :b)"),
                {"a": run_a_id, "b": run_b_id},
            )
            connection.execute(
                text("DELETE FROM source_subscriptions WHERE id IN (:a, :b)"),
                {"a": sub_a_id, "b": sub_b_id},
            )
            connection.execute(
                text("DELETE FROM organizations WHERE id IN (:a, :b)"),
                {"a": org_a, "b": org_b},
            )
        admin_engine.dispose()

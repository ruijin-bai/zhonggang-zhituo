import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import MembershipRecord, OpportunityRecord, OrganizationRecord, UserRecord, utc_now
from app.pursuit_db import PursuitWorkspaceRecord
from app.pursuit_delivery_db import PursuitReminderDeliveryRecord
from app.pursuit_reminder_db import PursuitReminderRecord


settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.database_url.startswith("postgresql"),
    reason="PostgreSQL reminder delivery RLS test requires PostgreSQL",
)


def _opportunity(opportunity_id: str, organization_id: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=organization_id,
        title="Delivery RLS",
        country="Nigeria",
        region="West Africa",
        sector="Port",
        stage="Tender",
        owner="Port Authority",
        estimated_value_usd_m=100,
        summary="RLS",
        score=70,
        grade="B",
        confidence=70,
        decision="WATCH",
        breakdown={
            "strategic_fit": 14,
            "project_maturity": 10,
            "financing": 10,
            "client_quality": 8,
            "capability_fit": 12,
            "local_position": 6,
            "competition": 6,
            "risk_control": 4,
        },
        pursuit_thesis="RLS",
        next_actions=[],
        is_demo=False,
    )


def test_postgres_reminder_delivery_rls_blocks_cross_tenant_access() -> None:
    suffix = uuid.uuid4().hex[:8]
    org_a = f"delivery-rls-org-a-{suffix}"
    org_b = f"delivery-rls-org-b-{suffix}"
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    opp_a = f"delivery-rls-opp-a-{suffix}"
    opp_b = f"delivery-rls-opp-b-{suffix}"
    ws_a = f"delivery-rls-ws-a-{suffix}"
    ws_b = f"delivery-rls-ws-b-{suffix}"
    rem_a = f"delivery-rls-rem-a-{suffix}"
    rem_b = f"delivery-rls-rem-b-{suffix}"
    delivery_a = f"delivery-rls-a-{suffix}"
    delivery_b = f"delivery-rls-b-{suffix}"
    role = f"zhituo_delivery_rls_{suffix}"
    password = f"DeliveryRls-{suffix}-Password-123!"

    admin_engine = create_engine(settings.database_url, pool_pre_ping=True)
    runtime_engine = None
    role_created = False
    try:
        with Session(admin_engine, expire_on_commit=False) as session:
            session.add_all([
                OrganizationRecord(id=org_a, name=f"Delivery A {suffix}", code=f"DEL-A-{suffix}", is_active=True),
                OrganizationRecord(id=org_b, name=f"Delivery B {suffix}", code=f"DEL-B-{suffix}", is_active=True),
                UserRecord(id=user_a, email=f"delivery-a-{suffix}@example.com", display_name="Delivery A", is_active=True),
                UserRecord(id=user_b, email=f"delivery-b-{suffix}@example.com", display_name="Delivery B", is_active=True),
            ])
            session.flush()
            membership_a = MembershipRecord(organization_id=org_a, user_id=user_a, role="manager", is_active=True)
            membership_b = MembershipRecord(organization_id=org_b, user_id=user_b, role="manager", is_active=True)
            session.add_all([membership_a, membership_b, _opportunity(opp_a, org_a), _opportunity(opp_b, org_b)])
            session.flush()
            now = utc_now()
            session.add_all([
                PursuitWorkspaceRecord(id=ws_a, organization_id=org_a, opportunity_id=opp_a, status="active", priority="high", lead_membership_id=membership_a.id, created_by_membership_id=membership_a.id, rationale="A"),
                PursuitWorkspaceRecord(id=ws_b, organization_id=org_b, opportunity_id=opp_b, status="active", priority="high", lead_membership_id=membership_b.id, created_by_membership_id=membership_b.id, rationale="B"),
            ])
            session.flush()
            session.add_all([
                PursuitReminderRecord(id=rem_a, organization_id=org_a, workspace_id=ws_a, opportunity_id=opp_a, recipient_membership_id=membership_a.id, reminder_type="workspace_review_due", severity="warning", status="open", title="A", message="A", dedupe_key=f"rem-a-{suffix}", escalation_level=0, occurrence_count=1, first_triggered_at=now, last_triggered_at=now, last_evaluated_at=now),
                PursuitReminderRecord(id=rem_b, organization_id=org_b, workspace_id=ws_b, opportunity_id=opp_b, recipient_membership_id=membership_b.id, reminder_type="workspace_review_due", severity="warning", status="open", title="B", message="B", dedupe_key=f"rem-b-{suffix}", escalation_level=0, occurrence_count=1, first_triggered_at=now, last_triggered_at=now, last_evaluated_at=now),
            ])
            session.flush()
            session.add_all([
                PursuitReminderDeliveryRecord(id=delivery_a, organization_id=org_a, reminder_id=rem_a, channel="email", recipient_membership_id=membership_a.id, recipient_address=f"delivery-a-{suffix}@example.com", delivery_key=f"email-a-{suffix}", status="pending", attempt_count=0, next_attempt_at=now, created_at=now, updated_at=now),
                PursuitReminderDeliveryRecord(id=delivery_b, organization_id=org_b, reminder_id=rem_b, channel="email", recipient_membership_id=membership_b.id, recipient_address=f"delivery-b-{suffix}@example.com", delivery_key=f"email-b-{suffix}", status="pending", attempt_count=0, next_attempt_at=now, created_at=now, updated_at=now),
            ])
            session.commit()
            membership_b_id = membership_b.id

        with admin_engine.begin() as connection:
            row = connection.execute(
                text("SELECT relrowsecurity FROM pg_class WHERE relname='pursuit_reminder_deliveries'")
            ).scalar_one()
            assert row is True
            policy = connection.execute(
                text("SELECT policyname FROM pg_policies WHERE tablename='pursuit_reminder_deliveries'")
            ).scalar_one()
            assert policy == "zhituo_tenant_isolation"
            connection.exec_driver_sql(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\' NOSUPERUSER NOBYPASSRLS')
            role_created = True
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            connection.exec_driver_sql(f'GRANT SELECT, INSERT ON TABLE pursuit_reminder_deliveries TO "{role}"')

        runtime_url = make_url(settings.database_url).set(username=role, password=password)
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        with runtime_engine.connect() as connection:
            connection.execute(text("SELECT set_config('app.current_organization_id', :org, false)"), {"org": org_a})
            visible = connection.execute(
                text("SELECT id FROM pursuit_reminder_deliveries WHERE id IN (:a, :b) ORDER BY id"),
                {"a": delivery_a, "b": delivery_b},
            ).scalars().all()
            assert visible == [delivery_a]

            with pytest.raises(DBAPIError, match="row-level security"):
                connection.execute(
                    text(
                        """
                        INSERT INTO pursuit_reminder_deliveries (
                            id, organization_id, reminder_id, channel, recipient_membership_id,
                            recipient_address, delivery_key, status, attempt_count,
                            next_attempt_at, created_at, updated_at
                        ) VALUES (
                            :id, :org, :reminder, 'email', :membership,
                            'forbidden@example.com', :delivery_key, 'pending', 0,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": f"forbidden-delivery-{suffix}",
                        "org": org_b,
                        "reminder": rem_b,
                        "membership": membership_b_id,
                        "delivery_key": f"forbidden-{suffix}",
                    },
                )
            connection.rollback()
    finally:
        if runtime_engine is not None:
            runtime_engine.dispose()
        with admin_engine.begin() as connection:
            if role_created:
                connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            connection.execute(text("DELETE FROM pursuit_reminder_deliveries WHERE id IN (:a, :b)"), {"a": delivery_a, "b": delivery_b})
            connection.execute(text("DELETE FROM pursuit_reminders WHERE id IN (:a, :b)"), {"a": rem_a, "b": rem_b})
            connection.execute(text("DELETE FROM pursuit_workspaces WHERE id IN (:a, :b)"), {"a": ws_a, "b": ws_b})
            connection.execute(text("DELETE FROM opportunities WHERE id IN (:a, :b)"), {"a": opp_a, "b": opp_b})
            connection.execute(text("DELETE FROM memberships WHERE user_id IN (:a, :b)"), {"a": user_a, "b": user_b})
            connection.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": user_a, "b": user_b})
            connection.execute(text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": org_a, "b": org_b})
        admin_engine.dispose()

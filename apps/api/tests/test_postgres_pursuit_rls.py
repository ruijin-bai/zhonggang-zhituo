import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import MembershipRecord, OpportunityRecord, OrganizationRecord, UserRecord, utc_now
from app.pursuit_db import PursuitWorkspaceRecord
from app.pursuit_reminder_db import PursuitReminderRecord


settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.database_url.startswith("postgresql"),
    reason="PostgreSQL Pursuit RLS integration test requires PostgreSQL",
)


PURSUIT_TABLES = (
    "pursuit_workspaces",
    "pursuit_participants",
    "pursuit_work_items",
    "pursuit_decision_gates",
    "pursuit_gate_reviews",
    "pursuit_decision_records",
    "pursuit_reminders",
)


def _opportunity(opportunity_id: str, organization_id: str, title: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=organization_id,
        title=title,
        country="Nigeria",
        region="West Africa",
        sector="Port",
        stage="Tender",
        owner="Port Authority",
        estimated_value_usd_m=100,
        summary="RLS test",
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


def test_postgres_pursuit_tables_enable_rls_and_block_cross_tenant_access() -> None:
    suffix = uuid.uuid4().hex[:8]
    org_a = f"pursuit-rls-org-a-{suffix}"
    org_b = f"pursuit-rls-org-b-{suffix}"
    opp_a = f"pursuit-rls-opp-a-{suffix}"
    opp_b = f"pursuit-rls-opp-b-{suffix}"
    workspace_a = f"pursuit-ws-a-{suffix}"
    workspace_b = f"pursuit-ws-b-{suffix}"
    reminder_a = f"pursuit-rem-a-{suffix}"
    reminder_b = f"pursuit-rem-b-{suffix}"
    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())
    role = f"zhituo_pursuit_rls_{suffix}"
    password = f"PursuitRls-{suffix}-Password-123!"

    admin_engine = create_engine(settings.database_url, pool_pre_ping=True)
    runtime_engine = None
    role_created = False
    try:
        with Session(admin_engine, expire_on_commit=False) as session:
            session.add_all(
                [
                    OrganizationRecord(id=org_a, name=f"Pursuit RLS A {suffix}", code=f"PUR-A-{suffix}", is_active=True),
                    OrganizationRecord(id=org_b, name=f"Pursuit RLS B {suffix}", code=f"PUR-B-{suffix}", is_active=True),
                    UserRecord(id=user_a_id, email=f"pursuit-a-{suffix}@example.com", display_name="Pursuit A", is_active=True),
                    UserRecord(id=user_b_id, email=f"pursuit-b-{suffix}@example.com", display_name="Pursuit B", is_active=True),
                ]
            )
            session.flush()
            membership_a = MembershipRecord(organization_id=org_a, user_id=user_a_id, role="manager", is_active=True)
            membership_b = MembershipRecord(organization_id=org_b, user_id=user_b_id, role="manager", is_active=True)
            session.add_all([membership_a, membership_b])
            session.add_all([
                _opportunity(opp_a, org_a, "Pursuit A Opportunity"),
                _opportunity(opp_b, org_b, "Pursuit B Opportunity"),
            ])
            session.flush()
            membership_a_id = membership_a.id
            membership_b_id = membership_b.id
            session.add_all([
                PursuitWorkspaceRecord(
                    id=workspace_a,
                    organization_id=org_a,
                    opportunity_id=opp_a,
                    status="active",
                    priority="high",
                    lead_membership_id=membership_a_id,
                    created_by_membership_id=membership_a_id,
                    rationale="A",
                ),
                PursuitWorkspaceRecord(
                    id=workspace_b,
                    organization_id=org_b,
                    opportunity_id=opp_b,
                    status="active",
                    priority="medium",
                    lead_membership_id=membership_b_id,
                    created_by_membership_id=membership_b_id,
                    rationale="B",
                ),
            ])
            session.flush()
            now = utc_now()
            session.add_all([
                PursuitReminderRecord(
                    id=reminder_a,
                    organization_id=org_a,
                    workspace_id=workspace_a,
                    opportunity_id=opp_a,
                    recipient_membership_id=membership_a_id,
                    reminder_type="workspace_review_due",
                    severity="warning",
                    status="open",
                    title="A Reminder",
                    message="A only",
                    dedupe_key=f"a:{suffix}",
                    escalation_level=0,
                    occurrence_count=1,
                    first_triggered_at=now,
                    last_triggered_at=now,
                    last_evaluated_at=now,
                ),
                PursuitReminderRecord(
                    id=reminder_b,
                    organization_id=org_b,
                    workspace_id=workspace_b,
                    opportunity_id=opp_b,
                    recipient_membership_id=membership_b_id,
                    reminder_type="workspace_review_due",
                    severity="warning",
                    status="open",
                    title="B Reminder",
                    message="B only",
                    dedupe_key=f"b:{suffix}",
                    escalation_level=0,
                    occurrence_count=1,
                    first_triggered_at=now,
                    last_triggered_at=now,
                    last_evaluated_at=now,
                ),
            ])
            session.commit()

        with admin_engine.begin() as connection:
            rls_rows = connection.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity
                    FROM pg_class c
                    WHERE c.relname = ANY(:tables)
                    """
                ),
                {"tables": list(PURSUIT_TABLES)},
            ).all()
            assert {row[0] for row in rls_rows} == set(PURSUIT_TABLES)
            assert all(row[1] is True for row in rls_rows)
            policy_rows = connection.execute(
                text(
                    """
                    SELECT tablename, policyname
                    FROM pg_policies
                    WHERE tablename = ANY(:tables)
                    """
                ),
                {"tables": list(PURSUIT_TABLES)},
            ).all()
            assert {row[0] for row in policy_rows} == set(PURSUIT_TABLES)
            assert all(row[1] == "zhituo_tenant_isolation" for row in policy_rows)

            connection.exec_driver_sql(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\' NOSUPERUSER NOBYPASSRLS')
            role_created = True
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            connection.exec_driver_sql(
                f'GRANT SELECT, INSERT ON TABLE pursuit_workspaces, pursuit_reminders TO "{role}"'
            )

        runtime_url = make_url(settings.database_url).set(username=role, password=password)
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        with runtime_engine.connect() as connection:
            connection.execute(
                text("SELECT set_config('app.current_organization_id', :org, false)"),
                {"org": org_a},
            )
            visible_workspaces = connection.execute(
                text("SELECT id FROM pursuit_workspaces WHERE id IN (:a, :b) ORDER BY id"),
                {"a": workspace_a, "b": workspace_b},
            ).scalars().all()
            visible_reminders = connection.execute(
                text("SELECT id FROM pursuit_reminders WHERE id IN (:a, :b) ORDER BY id"),
                {"a": reminder_a, "b": reminder_b},
            ).scalars().all()
            assert visible_workspaces == [workspace_a]
            assert visible_reminders == [reminder_a]

            with pytest.raises(DBAPIError, match="row-level security"):
                connection.execute(
                    text(
                        """
                        INSERT INTO pursuit_reminders (
                            id, organization_id, workspace_id, opportunity_id,
                            recipient_membership_id, reminder_type, severity, status,
                            title, message, dedupe_key, escalation_level, occurrence_count,
                            first_triggered_at, last_triggered_at, last_evaluated_at
                        ) VALUES (
                            :id, :org, :workspace, :opportunity, :membership,
                            'workspace_review_due', 'warning', 'open',
                            'Forbidden', 'cross tenant', :dedupe, 0, 1,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": f"forbidden-rem-{suffix}",
                        "org": org_b,
                        "workspace": workspace_b,
                        "opportunity": opp_b,
                        "membership": membership_b_id,
                        "dedupe": f"forbidden:{suffix}",
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
            connection.execute(text("DELETE FROM pursuit_reminders WHERE id IN (:a, :b)"), {"a": reminder_a, "b": reminder_b})
            connection.execute(text("DELETE FROM pursuit_workspaces WHERE id IN (:a, :b)"), {"a": workspace_a, "b": workspace_b})
            connection.execute(text("DELETE FROM opportunities WHERE id IN (:a, :b)"), {"a": opp_a, "b": opp_b})
            connection.execute(text("DELETE FROM memberships WHERE user_id IN (:a, :b)"), {"a": user_a_id, "b": user_b_id})
            connection.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": user_a_id, "b": user_b_id})
            connection.execute(text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": org_a, "b": org_b})
        admin_engine.dispose()

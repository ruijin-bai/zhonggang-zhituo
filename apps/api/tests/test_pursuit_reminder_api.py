from datetime import timedelta
import uuid

from fastapi import Request
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import (
    AuditLogRecord,
    Base,
    IdempotencyRecord,
    MembershipRecord,
    OpportunityRecord,
    OrganizationRecord,
    UserRecord,
    set_tenant_context,
    utc_now,
)
from app.pursuit_reminder_api import pursuit_reminder_acknowledge
from app.pursuit_reminder_db import PursuitReminderRecord
from app.pursuit_reminders import reconcile_pursuit_reminders
from app.pursuit_service import create_work_item, ensure_workspace
from app.security import Principal


def _request(key: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "PUT",
            "scheme": "http",
            "path": "/api/pursuit/reminders/reminder/acknowledge",
            "raw_path": b"/api/pursuit/reminders/reminder/acknowledge",
            "query_string": b"",
            "headers": [(b"idempotency-key", key.encode("utf-8"))],
            "client": ("test", 1234),
            "server": ("test", 80),
        }
    )


def _opportunity(opportunity_id: str, organization_id: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=organization_id,
        title="Reminder API Project",
        country="Nigeria",
        region="West Africa",
        sector="Road",
        stage="Tender",
        owner="Agency",
        estimated_value_usd_m=50,
        summary="API idempotency",
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
        pursuit_thesis="Test",
        next_actions=[],
        is_demo=False,
    )


def test_reminder_acknowledgement_replays_without_duplicate_audit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        org = OrganizationRecord(
            name=f"Reminder API {uuid.uuid4().hex[:6]}",
            code=f"rapi-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        manager = UserRecord(
            email=f"manager-{uuid.uuid4().hex[:6]}@example.com",
            display_name="Manager",
            is_active=True,
        )
        analyst = UserRecord(
            email=f"analyst-{uuid.uuid4().hex[:6]}@example.com",
            display_name="Analyst",
            is_active=True,
        )
        session.add_all([org, manager, analyst])
        session.flush()
        manager_membership = MembershipRecord(
            organization_id=org.id,
            user_id=manager.id,
            role="manager",
            is_active=True,
        )
        analyst_membership = MembershipRecord(
            organization_id=org.id,
            user_id=analyst.id,
            role="analyst",
            is_active=True,
        )
        session.add_all([manager_membership, analyst_membership])
        opportunity_id = f"opp-{uuid.uuid4().hex[:8]}"
        session.add(_opportunity(opportunity_id, org.id))
        session.commit()
        set_tenant_context(session, org.id)

        manager_principal = Principal(
            user_id=manager.id,
            email=manager.email,
            display_name=manager.display_name,
            organization_id=org.id,
            organization_name=org.name,
            role="manager",
        )
        analyst_principal = Principal(
            user_id=analyst.id,
            email=analyst.email,
            display_name=analyst.display_name,
            organization_id=org.id,
            organization_name=org.name,
            role="analyst",
        )
        workspace = ensure_workspace(
            session,
            opportunity_id=opportunity_id,
            principal=manager_principal,
        )
        create_work_item(
            session,
            workspace_id=workspace.id,
            principal=manager_principal,
            title="准备客户会议材料",
            assignee_membership_id=analyst_membership.id,
            due_at=utc_now() + timedelta(hours=1),
        )
        session.commit()
        reconcile_pursuit_reminders(session)
        reminder = session.scalar(
            select(PursuitReminderRecord).where(
                PursuitReminderRecord.reminder_type == "work_due_soon"
            )
        )
        assert reminder is not None

        key = "pursuit-reminder-ack-stable-key"
        first = pursuit_reminder_acknowledge(
            reminder.id,
            _request(key),
            db=session,
            principal=analyst_principal,
        )
        second = pursuit_reminder_acknowledge(
            reminder.id,
            _request(key),
            db=session,
            principal=analyst_principal,
        )

        assert first == second
        assert first["status"] == "acknowledged"
        assert session.get(PursuitReminderRecord, reminder.id).status == "acknowledged"
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        assert session.scalar(
            select(func.count())
            .select_from(AuditLogRecord)
            .where(AuditLogRecord.action == "pursuit.reminder.acknowledge")
        ) == 1

    engine.dispose()

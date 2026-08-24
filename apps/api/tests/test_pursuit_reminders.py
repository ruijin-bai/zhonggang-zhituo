from datetime import timedelta
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import (
    Base,
    MembershipRecord,
    OpportunityRecord,
    OrganizationRecord,
    UserRecord,
    set_tenant_context,
    utc_now,
)
from app.pursuit_db import PursuitWorkItemRecord
from app.pursuit_reminder_db import PursuitReminderRecord
from app.pursuit_reminders import (
    acknowledge_reminder,
    reconcile_pursuit_reminders,
    reminders_for_member,
)
from app.pursuit_service import (
    create_work_item,
    ensure_workspace,
    open_gate,
    record_gate_decision,
    request_gate_review,
    update_work_item,
)
from app.security import Principal


def _org(session: Session) -> OrganizationRecord:
    row = OrganizationRecord(
        name=f"Reminder Org {uuid.uuid4().hex[:6]}",
        code=f"rem-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    session.add(row)
    session.flush()
    return row


def _member(
    session: Session,
    org: OrganizationRecord,
    name: str,
    role: str,
) -> tuple[UserRecord, MembershipRecord]:
    user = UserRecord(
        email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        display_name=name,
        is_active=True,
    )
    session.add(user)
    session.flush()
    membership = MembershipRecord(
        organization_id=org.id,
        user_id=user.id,
        role=role,
        is_active=True,
    )
    session.add(membership)
    session.flush()
    return user, membership


def _principal(
    user: UserRecord,
    membership: MembershipRecord,
    org: OrganizationRecord,
) -> Principal:
    return Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=org.id,
        organization_name=org.name,
        role=membership.role,
    )


def _opportunity(opportunity_id: str, org_id: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=org_id,
        title="Reminder Lifecycle Project",
        country="Nigeria",
        region="West Africa",
        sector="Port",
        stage="Tender",
        owner="Public Authority",
        estimated_value_usd_m=100,
        summary="Reminder lifecycle test",
        score=74,
        grade="B",
        confidence=76,
        decision="WATCH",
        breakdown={
            "strategic_fit": 16,
            "project_maturity": 11,
            "financing": 10,
            "client_quality": 8,
            "capability_fit": 12,
            "local_position": 7,
            "competition": 6,
            "risk_control": 4,
        },
        pursuit_thesis="Test pursuit reminders",
        next_actions=[],
        is_demo=False,
    )


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    org = _org(session)
    manager_user, manager_membership = _member(session, org, "Manager", "manager")
    analyst_user, analyst_membership = _member(session, org, "Analyst", "analyst")
    opportunity_id = f"opp-rem-{uuid.uuid4().hex[:8]}"
    session.add(_opportunity(opportunity_id, org.id))
    session.commit()
    set_tenant_context(session, org.id)
    manager = _principal(manager_user, manager_membership, org)
    analyst = _principal(analyst_user, analyst_membership, org)
    workspace = ensure_workspace(
        session,
        opportunity_id=opportunity_id,
        principal=manager,
        priority="high",
    )
    session.commit()
    return engine, session, workspace, manager, analyst, manager_membership, analyst_membership


def test_due_reminder_dedupes_escalates_resolves_and_reopens() -> None:
    engine, session, workspace, manager, analyst, manager_membership, analyst_membership = _setup()
    now = utc_now()
    item = create_work_item(
        session,
        workspace_id=workspace.id,
        principal=manager,
        title="核实采购时间",
        assignee_membership_id=analyst_membership.id,
        priority="high",
        due_at=now + timedelta(hours=1),
    )
    session.commit()

    first = reconcile_pursuit_reminders(session, now=now)
    second = reconcile_pursuit_reminders(session, now=now + timedelta(minutes=5))
    reminders = session.scalars(select(PursuitReminderRecord)).all()

    assert first["active_conditions"] == 1
    assert second["active_conditions"] == 1
    assert len(reminders) == 1
    due_soon = reminders[0]
    assert due_soon.reminder_type == "work_due_soon"
    assert due_soon.recipient_membership_id == analyst_membership.id
    assert due_soon.occurrence_count == 1
    assert due_soon.escalation_level == 0

    acknowledge_reminder(session, reminder_id=due_soon.id, principal=analyst)
    session.commit()
    assert due_soon.status == "acknowledged"

    item.due_at = now - timedelta(hours=100)
    session.commit()
    reconcile_pursuit_reminders(session, now=now)
    rows = session.scalars(select(PursuitReminderRecord)).all()
    overdue = next(row for row in rows if row.reminder_type == "work_overdue")
    assert due_soon.status == "resolved"
    assert overdue.status == "open"
    assert overdue.severity == "critical"
    assert overdue.escalation_level == 1
    assert overdue.escalated_to_membership_id == manager_membership.id

    manager_inbox = reminders_for_member(session, manager)
    analyst_inbox = reminders_for_member(session, analyst)
    assert any(item["id"] == overdue.id and item["is_escalation"] for item in manager_inbox["items"])
    assert any(item["id"] == overdue.id for item in analyst_inbox["items"])

    update_work_item(session, work_item_id=item.id, status="done")
    session.commit()
    reconcile_pursuit_reminders(session, now=now + timedelta(hours=1))
    assert overdue.status == "resolved"

    update_work_item(
        session,
        work_item_id=item.id,
        status="open",
        due_at=now + timedelta(hours=2),
    )
    session.commit()
    reconcile_pursuit_reminders(session, now=now + timedelta(hours=1))
    assert due_soon.status == "open"
    assert due_soon.occurrence_count == 2

    session.close()
    engine.dispose()


def test_blocked_since_is_stateful_and_drives_escalation() -> None:
    engine, session, workspace, manager, analyst, manager_membership, analyst_membership = _setup()
    now = utc_now()
    item = create_work_item(
        session,
        workspace_id=workspace.id,
        principal=manager,
        title="获取融资约束",
        assignee_membership_id=analyst_membership.id,
    )
    update_work_item(
        session,
        work_item_id=item.id,
        status="blocked",
        blocked_reason="等待融资方正式反馈",
    )
    session.commit()
    assert item.blocked_since is not None

    item.blocked_since = now - timedelta(hours=30)
    session.commit()
    reconcile_pursuit_reminders(session, now=now)
    reminder = session.scalar(
        select(PursuitReminderRecord).where(
            PursuitReminderRecord.reminder_type == "work_blocked"
        )
    )
    assert reminder is not None
    assert reminder.severity == "critical"
    assert reminder.escalated_to_membership_id == manager_membership.id

    update_work_item(session, work_item_id=item.id, status="in_progress")
    session.commit()
    assert item.blocked_since is None
    reconcile_pursuit_reminders(session, now=now + timedelta(minutes=10))
    assert reminder.status == "resolved"

    session.close()
    engine.dispose()


def test_pending_review_escalates_but_terminal_gate_stops_reminder() -> None:
    engine, session, workspace, manager, analyst, manager_membership, analyst_membership = _setup()
    now = utc_now()
    gate = open_gate(
        session,
        workspace_id=workspace.id,
        principal=manager,
        gate_type="bid",
        title="正式投标 Go/No-Go",
        due_at=None,
    )
    review = request_gate_review(
        session,
        gate_id=gate.id,
        reviewer_membership_id=analyst_membership.id,
        principal=manager,
    )
    review.requested_at = now - timedelta(hours=60)
    session.commit()

    reconcile_pursuit_reminders(session, now=now)
    reminder = session.scalar(
        select(PursuitReminderRecord).where(
            PursuitReminderRecord.reminder_type == "review_pending"
        )
    )
    assert reminder is not None
    assert reminder.recipient_membership_id == analyst_membership.id
    assert reminder.escalated_to_membership_id == manager_membership.id
    assert reminder.escalation_level == 1

    record_gate_decision(
        session,
        gate_id=gate.id,
        decision="NO_GO",
        rationale="关键商业条件不成立",
        principal=manager,
    )
    session.commit()
    assert review.status == "pending"
    assert gate.status == "decided"

    reconcile_pursuit_reminders(session, now=now + timedelta(hours=1))
    assert reminder.status == "resolved"

    session.close()
    engine.dispose()

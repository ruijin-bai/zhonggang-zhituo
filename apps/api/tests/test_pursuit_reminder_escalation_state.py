from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, set_tenant_context, utc_now
from app.pursuit_db import PursuitWorkspaceRecord
from app.pursuit_reminder_db import PursuitReminderRecord
from app.pursuit_reminders import _ensure_reminder


def test_acknowledged_reminder_reopens_when_escalation_level_increases() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    set_tenant_context(session, "org-escalation")

    now = utc_now()
    original_trigger = now - timedelta(hours=12)
    workspace = PursuitWorkspaceRecord(
        id="workspace-escalation",
        organization_id="org-escalation",
        opportunity_id="opportunity-escalation",
        status="active",
        priority="high",
        lead_membership_id=1,
        rationale="test",
    )
    reminder = PursuitReminderRecord(
        id="reminder-escalation",
        organization_id="org-escalation",
        workspace_id=workspace.id,
        opportunity_id=workspace.opportunity_id,
        recipient_membership_id=2,
        escalated_to_membership_id=None,
        work_item_id="work-escalation",
        gate_id=None,
        review_id=None,
        reminder_type="work_blocked",
        severity="high",
        status="acknowledged",
        title="blocked",
        message="blocked",
        dedupe_key="work_blocked:work-escalation:2",
        source_due_at=None,
        escalation_level=0,
        occurrence_count=1,
        first_triggered_at=original_trigger,
        last_triggered_at=original_trigger,
        last_evaluated_at=original_trigger,
        acknowledged_at=original_trigger,
        resolved_at=None,
    )
    session.add(reminder)
    session.commit()

    returned = _ensure_reminder(
        session,
        active_keys=set(),
        workspace=workspace,
        recipient_membership_id=2,
        reminder_type="work_blocked",
        severity="critical",
        title="blocked escalated",
        message="escalated to lead",
        work_item_id="work-escalation",
        escalated_to_membership_id=1,
        escalation_level=1,
        now=now,
    )
    session.flush()

    assert returned.id == reminder.id
    assert returned.status == "open"
    assert returned.acknowledged_at is None
    assert returned.escalation_level == 1
    assert returned.escalated_to_membership_id == 1
    assert returned.occurrence_count == 1
    assert returned.last_triggered_at == now

    session.close()
    engine.dispose()

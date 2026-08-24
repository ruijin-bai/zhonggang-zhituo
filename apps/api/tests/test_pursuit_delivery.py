from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import (
    Base,
    MembershipRecord,
    OpportunityRecord,
    OrganizationRecord,
    UserRecord,
    set_tenant_context,
    utc_now,
)
from app.pursuit_db import PursuitWorkspaceRecord
from app.pursuit_delivery import (
    claim_reminder_email_deliveries,
    deliver_reminder_email,
    stage_reminder_email_deliveries,
)
from app.pursuit_delivery_db import PursuitReminderDeliveryRecord
from app.pursuit_reminder_db import PursuitReminderRecord


class FakeTransport:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        if self.error is not None:
            raise self.error
        return str(message["Message-ID"])


def _settings(**overrides) -> Settings:
    values = {
        "pursuit_email_delivery_enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_from_email": "zhituo@example.com",
        "smtp_from_name": "中港智拓",
        "smtp_starttls": True,
        "smtp_use_ssl": False,
        "notification_public_base_url": "https://zhituo.example.com",
    }
    values.update(overrides)
    return Settings(**values)


def _opportunity(opportunity_id: str, organization_id: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=organization_id,
        title="Email Delivery Test Project",
        country="Nigeria",
        region="West Africa",
        sector="Port",
        stage="Tender",
        owner="Port Authority",
        estimated_value_usd_m=100,
        summary="delivery test",
        score=75,
        grade="B",
        confidence=80,
        decision="WATCH",
        breakdown={
            "strategic_fit": 16,
            "project_maturity": 11,
            "financing": 10,
            "client_quality": 8,
            "capability_fit": 13,
            "local_position": 7,
            "competition": 6,
            "risk_control": 4,
        },
        pursuit_thesis="delivery test",
        next_actions=[],
        is_demo=False,
    )


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    org = OrganizationRecord(
        name="Delivery Org",
        code=f"delivery-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    manager_user = UserRecord(
        email=f"manager-{uuid.uuid4().hex[:6]}@example.com",
        display_name="Pursuit Lead",
        is_active=True,
    )
    analyst_user = UserRecord(
        email=f"analyst-{uuid.uuid4().hex[:6]}@example.com",
        display_name="Pursuit Analyst",
        is_active=True,
    )
    session.add_all([org, manager_user, analyst_user])
    session.flush()
    manager = MembershipRecord(
        organization_id=org.id,
        user_id=manager_user.id,
        role="manager",
        is_active=True,
    )
    analyst = MembershipRecord(
        organization_id=org.id,
        user_id=analyst_user.id,
        role="analyst",
        is_active=True,
    )
    session.add_all([manager, analyst])
    opportunity_id = f"delivery-opp-{uuid.uuid4().hex[:8]}"
    session.add(_opportunity(opportunity_id, org.id))
    session.flush()
    workspace = PursuitWorkspaceRecord(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        opportunity_id=opportunity_id,
        status="active",
        priority="high",
        lead_membership_id=manager.id,
        created_by_membership_id=manager.id,
        rationale="test",
    )
    reminder = PursuitReminderRecord(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        workspace_id=workspace.id,
        opportunity_id=opportunity_id,
        recipient_membership_id=analyst.id,
        escalated_to_membership_id=None,
        reminder_type="work_overdue",
        severity="high",
        status="open",
        title="经营工作已逾期：确认采购计划",
        message="Work Item 已逾期，请更新状态。",
        dedupe_key=f"delivery-reminder-{uuid.uuid4().hex}",
        source_due_at=utc_now() - timedelta(hours=2),
        escalation_level=0,
        occurrence_count=1,
        first_triggered_at=utc_now(),
        last_triggered_at=utc_now(),
        last_evaluated_at=utc_now(),
    )
    session.add_all([workspace, reminder])
    session.commit()
    set_tenant_context(session, org.id)
    return engine, session, reminder, manager, analyst, manager_user, analyst_user


def test_staging_dedupes_and_escalation_targets_lead() -> None:
    engine, session, reminder, manager, analyst, manager_user, analyst_user = _setup()
    settings = _settings()

    first = stage_reminder_email_deliveries(session, settings=settings)
    second = stage_reminder_email_deliveries(session, settings=settings)
    rows = session.scalars(
        select(PursuitReminderDeliveryRecord).order_by(PursuitReminderDeliveryRecord.created_at.asc())
    ).all()

    assert first["created"] == 1
    assert second["created"] == 0
    assert len(rows) == 1
    assert rows[0].recipient_membership_id == analyst.id
    assert rows[0].recipient_address == analyst_user.email

    reminder.escalation_level = 1
    reminder.escalated_to_membership_id = manager.id
    reminder.severity = "critical"
    session.commit()
    escalated = stage_reminder_email_deliveries(session, settings=settings)
    rows = session.scalars(select(PursuitReminderDeliveryRecord)).all()

    assert escalated["created"] == 1
    assert len(rows) == 2
    lead_delivery = next(row for row in rows if row.recipient_membership_id == manager.id)
    assert lead_delivery.recipient_address == manager_user.email
    assert ":esc:1:" in lead_delivery.delivery_key

    session.close()
    engine.dispose()


def test_claim_and_send_uses_deterministic_message_id_and_marks_sent() -> None:
    engine, session, reminder, manager, analyst, manager_user, analyst_user = _setup()
    settings = _settings()
    stage_reminder_email_deliveries(session, settings=settings)
    claims = claim_reminder_email_deliveries(session, settings=settings)
    assert len(claims) == 1
    delivery_id, token = claims[0]

    transport = FakeTransport()
    result = deliver_reminder_email(
        session,
        delivery_id,
        lease_token=token,
        settings=settings,
        transport=transport,
    )
    delivery = session.get(PursuitReminderDeliveryRecord, delivery_id)

    assert result["status"] == "sent"
    assert delivery.status == "sent"
    assert delivery.attempt_count == 1
    assert delivery.message_id == f"<zhituo-{delivery_id}@example.com>"
    assert delivery.sent_at is not None
    assert len(transport.messages) == 1
    message = transport.messages[0]
    assert message["To"] == analyst_user.email
    assert message["Message-ID"] == delivery.message_id
    assert message["X-Zhituo-Reminder-ID"] == reminder.id
    assert "Email Delivery Test Project" in message.get_body(preferencelist=("plain",)).get_content()
    assert "/pursuit/opportunities/" in message.get_body(preferencelist=("plain",)).get_content()

    session.close()
    engine.dispose()


def test_send_failure_retries_and_acknowledged_reminder_cancels_stale_delivery() -> None:
    engine, session, reminder, manager, analyst, manager_user, analyst_user = _setup()
    settings = _settings(pursuit_email_max_attempts=2)
    stage_reminder_email_deliveries(session, settings=settings)
    delivery_id, token = claim_reminder_email_deliveries(session, settings=settings)[0]

    failed = deliver_reminder_email(
        session,
        delivery_id,
        lease_token=token,
        settings=settings,
        transport=FakeTransport(RuntimeError("smtp unavailable")),
    )
    delivery = session.get(PursuitReminderDeliveryRecord, delivery_id)
    assert failed["status"] == "retry"
    assert delivery.status == "retry"
    assert delivery.attempt_count == 1
    assert "smtp unavailable" in (delivery.error_detail or "")

    delivery.next_attempt_at = utc_now() - timedelta(seconds=1)
    session.commit()
    delivery_id, token = claim_reminder_email_deliveries(session, settings=settings)[0]
    reminder.status = "acknowledged"
    reminder.acknowledged_at = utc_now()
    session.commit()

    cancelled = deliver_reminder_email(
        session,
        delivery_id,
        lease_token=token,
        settings=settings,
        transport=FakeTransport(),
    )
    assert cancelled["status"] == "cancelled"
    assert session.get(PursuitReminderDeliveryRecord, delivery_id).status == "cancelled"

    session.close()
    engine.dispose()


def test_email_settings_require_transport_configuration() -> None:
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        Settings(
            pursuit_email_delivery_enabled=True,
            smtp_from_email="zhituo@example.com",
        )
    with pytest.raises(ValidationError, match="cannot both be true"):
        Settings(
            smtp_use_ssl=True,
            smtp_starttls=True,
        )

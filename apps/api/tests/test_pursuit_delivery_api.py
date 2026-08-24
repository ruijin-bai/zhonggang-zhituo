from __future__ import annotations

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
from app.pursuit_db import PursuitWorkspaceRecord
from app.pursuit_delivery_api import pursuit_reminder_delivery_retry
from app.pursuit_delivery_db import PursuitReminderDeliveryRecord
from app.pursuit_reminder_db import PursuitReminderRecord
from app.security import Principal


def _request(key: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/pursuit/reminder-deliveries/delivery/retry",
            "raw_path": b"/api/pursuit/reminder-deliveries/delivery/retry",
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
        title="Delivery API Test",
        country="Nigeria",
        region="West Africa",
        sector="Port",
        stage="Tender",
        owner="Authority",
        estimated_value_usd_m=100,
        summary="Delivery API idempotency",
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


def test_failed_delivery_manual_retry_replays_and_resets_budget_once() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        org = OrganizationRecord(
            name=f"Delivery API {uuid.uuid4().hex[:6]}",
            code=f"dapi-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        user = UserRecord(
            email=f"manager-{uuid.uuid4().hex[:6]}@example.com",
            display_name="Delivery Manager",
            is_active=True,
        )
        session.add_all([org, user])
        session.flush()
        membership = MembershipRecord(
            organization_id=org.id,
            user_id=user.id,
            role="manager",
            is_active=True,
        )
        session.add(membership)
        opportunity_id = f"delivery-api-opp-{uuid.uuid4().hex[:8]}"
        session.add(_opportunity(opportunity_id, org.id))
        session.flush()
        workspace = PursuitWorkspaceRecord(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            opportunity_id=opportunity_id,
            status="active",
            priority="high",
            lead_membership_id=membership.id,
            created_by_membership_id=membership.id,
            rationale="test",
        )
        reminder = PursuitReminderRecord(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            workspace_id=workspace.id,
            opportunity_id=opportunity_id,
            recipient_membership_id=membership.id,
            reminder_type="work_overdue",
            severity="high",
            status="open",
            title="Delivery retry",
            message="Retry me",
            dedupe_key=f"delivery-api-rem-{uuid.uuid4().hex}",
            escalation_level=0,
            occurrence_count=1,
            first_triggered_at=utc_now(),
            last_triggered_at=utc_now(),
            last_evaluated_at=utc_now(),
        )
        session.add_all([workspace, reminder])
        session.flush()
        delivery = PursuitReminderDeliveryRecord(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            reminder_id=reminder.id,
            channel="email",
            recipient_membership_id=membership.id,
            recipient_address=user.email,
            delivery_key=f"delivery-api-{uuid.uuid4().hex}",
            status="failed",
            attempt_count=5,
            next_attempt_at=utc_now(),
            error_detail="smtp unavailable",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(delivery)
        session.commit()
        set_tenant_context(session, org.id)

        principal = Principal(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            organization_id=org.id,
            organization_name=org.name,
            role="manager",
        )
        key = "pursuit-delivery-retry-stable-key"
        first = pursuit_reminder_delivery_retry(
            delivery.id,
            _request(key),
            db=session,
            principal=principal,
        )
        second = pursuit_reminder_delivery_retry(
            delivery.id,
            _request(key),
            db=session,
            principal=principal,
        )

        assert first == second
        assert first["status"] == "retry"
        assert first["attempt_count"] == 0
        stored = session.get(PursuitReminderDeliveryRecord, delivery.id)
        assert stored.status == "retry"
        assert stored.attempt_count == 0
        assert stored.error_detail is None
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        assert session.scalar(
            select(func.count())
            .select_from(AuditLogRecord)
            .where(AuditLogRecord.action == "pursuit.reminder_delivery.retry")
        ) == 1
        audit = session.scalar(
            select(AuditLogRecord).where(
                AuditLogRecord.action == "pursuit.reminder_delivery.retry"
            )
        )
        assert audit is not None
        assert audit.details["previous_attempt_count"] == 5

    engine.dispose()

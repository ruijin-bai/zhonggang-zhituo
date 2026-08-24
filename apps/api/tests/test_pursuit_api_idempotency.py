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
)
from app.pursuit_api import WorkItemCreate, pursuit_create_work_item
from app.pursuit_db import PursuitWorkItemRecord
from app.pursuit_service import ensure_workspace
from app.security import Principal


def _request(key: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/pursuit/workspaces/ws/work-items",
            "raw_path": b"/api/pursuit/workspaces/ws/work-items",
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
        title="Pursuit Idempotency",
        country="Nigeria",
        region="West Africa",
        sector="Port",
        stage="Tender",
        owner="Authority",
        estimated_value_usd_m=100,
        summary="Test",
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


def test_work_item_create_replays_without_duplicate_work_or_audit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        organization = OrganizationRecord(
            id=str(uuid.uuid4()),
            name="Pursuit API Org",
            code=f"PUR-API-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        user = UserRecord(
            id=str(uuid.uuid4()),
            email=f"manager-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Pursuit Manager",
            is_active=True,
        )
        session.add_all([organization, user])
        session.flush()
        membership = MembershipRecord(
            organization_id=organization.id,
            user_id=user.id,
            role="manager",
            is_active=True,
        )
        session.add(membership)
        opportunity_id = f"opp-{uuid.uuid4().hex[:8]}"
        session.add(_opportunity(opportunity_id, organization.id))
        session.commit()
        set_tenant_context(session, organization.id)

        principal = Principal(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            organization_id=organization.id,
            organization_name=organization.name,
            role="manager",
        )
        workspace = ensure_workspace(
            session,
            opportunity_id=opportunity_id,
            principal=principal,
        )
        session.commit()
        body = WorkItemCreate(
            title="核实融资批准状态",
            assignee_membership_id=membership.id,
            priority="high",
        )

        first = pursuit_create_work_item(
            workspace.id,
            body,
            _request("pursuit-workitem-stable-key"),
            db=session,
            principal=principal,
        )
        second = pursuit_create_work_item(
            workspace.id,
            body,
            _request("pursuit-workitem-stable-key"),
            db=session,
            principal=principal,
        )

        assert second == first
        assert session.scalar(select(func.count()).select_from(PursuitWorkItemRecord)) == 1
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        assert session.scalar(
            select(func.count())
            .select_from(AuditLogRecord)
            .where(AuditLogRecord.action == "pursuit.work_item.create")
        ) == 1

    engine.dispose()

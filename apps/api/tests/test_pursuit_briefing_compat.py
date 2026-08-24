import uuid
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.briefing import daily_brief
from app.db import (
    Base,
    OpportunityRecord,
    OrganizationRecord,
    PursuitActionRecord,
    set_tenant_context,
    utc_now,
)
from app.pursuit_db import PursuitWorkItemRecord, PursuitWorkspaceRecord


def _opportunity(org_id: str, opportunity_id: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=org_id,
        title="Canonical Pursuit Briefing",
        country="Nigeria",
        region="West Africa",
        sector="Port",
        stage="Tender",
        owner="Port Authority",
        estimated_value_usd_m=120,
        summary="Test",
        score=72,
        grade="B",
        confidence=70,
        decision="WATCH",
        breakdown={
            "strategic_fit": 15,
            "project_maturity": 10,
            "financing": 10,
            "client_quality": 8,
            "capability_fit": 12,
            "local_position": 6,
            "competition": 7,
            "risk_control": 4,
        },
        pursuit_thesis="Test",
        next_actions=[],
        is_demo=False,
    )


def test_daily_brief_prefers_canonical_work_item_without_double_counting_legacy_action() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = utc_now()

    with Session(engine, expire_on_commit=False) as session:
        org = OrganizationRecord(
            id=str(uuid.uuid4()),
            name=f"Brief Compat {uuid.uuid4().hex[:6]}",
            code=f"BR-COMPAT-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(org)
        session.flush()
        opportunity_id = f"opp-{uuid.uuid4().hex[:8]}"
        session.add(_opportunity(org.id, opportunity_id))
        session.flush()

        legacy = PursuitActionRecord(
            organization_id=org.id,
            opportunity_id=opportunity_id,
            title="核实融资批复",
            owner="Legacy Owner",
            status="open",
            priority="high",
            due_at=now - timedelta(days=1),
            note="",
        )
        session.add(legacy)
        session.flush()
        workspace = PursuitWorkspaceRecord(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            opportunity_id=opportunity_id,
            status="active",
            priority="high",
            rationale="",
            next_review_at=None,
        )
        session.add(workspace)
        session.flush()
        canonical = PursuitWorkItemRecord(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            workspace_id=workspace.id,
            opportunity_id=opportunity_id,
            work_type="action",
            title=legacy.title,
            description="",
            assignee_membership_id=None,
            created_by_membership_id=None,
            legacy_owner_text=legacy.owner,
            status="in_progress",
            priority="high",
            due_at=legacy.due_at,
            blocked_reason=None,
            dependency_work_item_id=None,
            source_action_id=legacy.id,
            completed_at=None,
        )
        session.add(canonical)
        session.commit()

        set_tenant_context(session, org.id)
        brief = daily_brief(session, limit=10)

        assert brief["summary"]["overdue_actions"] == 1
        matching = [item for item in brief["attention"] if item.get("title") == "核实融资批复"]
        assert len(matching) == 1
        assert matching[0]["kind"] == "overdue_work_item"
        assert matching[0]["source"] == "pursuit_work_item"
        assert matching[0]["owner"] == "Legacy Owner"

    engine.dispose()

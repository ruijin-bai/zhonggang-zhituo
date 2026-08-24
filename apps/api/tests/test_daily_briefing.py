import uuid
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.briefing import daily_brief
from app.db import (
    Base,
    OpportunityDraftRecord,
    OpportunityEventRecord,
    OpportunityRecord,
    OrganizationRecord,
    PursuitActionRecord,
    PursuitAlertRecord,
    WatchItemRecord,
    set_tenant_context,
    utc_now,
)


def _org(session: Session, label: str) -> OrganizationRecord:
    row = OrganizationRecord(
        id=str(uuid.uuid4()),
        name=f"Brief {label}",
        code=f"brief-{label.lower()}-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    session.add(row)
    session.flush()
    return row


def _opportunity(organization_id: str, suffix: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=f"opp-{suffix}-{uuid.uuid4().hex[:6]}",
        organization_id=organization_id,
        title=f"{suffix} Port Corridor",
        country="Nigeria",
        region="West Africa",
        sector="Transport",
        stage="Procurement",
        owner=f"{suffix} Authority",
        estimated_value_usd_m=100,
        summary=f"{suffix} summary",
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
        pursuit_thesis=f"{suffix} thesis",
        next_actions=[],
        is_demo=False,
    )


def _candidate(organization_id: str, suffix: str) -> OpportunityDraftRecord:
    now = utc_now()
    return OpportunityDraftRecord(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        status="pending",
        discovery={
            "project_detected": True,
            "title": f"{suffix} Candidate",
            "country": "Nigeria",
            "region": "West Africa",
            "sector": "Road",
            "stage": "Procurement",
            "owner": f"{suffix} Agency",
            "estimated_value_usd_m": None,
            "summary": f"{suffix} candidate summary",
            "confidence": 0.9,
            "facts": [],
            "parties": [],
        },
        source_url=f"https://example.com/{suffix.lower()}",
        source_title=f"{suffix} Notice",
        publisher=f"{suffix} Agency",
        published_at="2026-08-24",
        source_rank="A",
        raw_text="",
        duplicate_matches=[],
        is_demo=False,
        created_at=now,
        updated_at=now,
    )


def test_daily_brief_is_tenant_scoped_across_all_operating_inputs() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = utc_now()

    with Session(engine) as session:
        org_a = _org(session, "A")
        org_b = _org(session, "B")
        opp_a = _opportunity(org_a.id, "A")
        opp_b = _opportunity(org_b.id, "B")
        session.add_all([opp_a, opp_b])
        session.flush()

        session.add_all([
            _candidate(org_a.id, "A"),
            _candidate(org_b.id, "B"),
            OpportunityEventRecord(
                organization_id=org_a.id,
                opportunity_id=opp_a.id,
                event_type="financing_updated",
                occurred_at=now - timedelta(hours=1),
                payload={"marker": "A-event"},
            ),
            OpportunityEventRecord(
                organization_id=org_b.id,
                opportunity_id=opp_b.id,
                event_type="financing_updated",
                occurred_at=now - timedelta(hours=1),
                payload={"marker": "B-event"},
            ),
            PursuitActionRecord(
                organization_id=org_a.id,
                opportunity_id=opp_a.id,
                title="A overdue action",
                owner="Alice",
                status="open",
                priority="high",
                due_at=now - timedelta(days=1),
                note="",
            ),
            PursuitActionRecord(
                organization_id=org_b.id,
                opportunity_id=opp_b.id,
                title="B overdue action",
                owner="Bob",
                status="open",
                priority="high",
                due_at=now - timedelta(days=1),
                note="",
            ),
            PursuitAlertRecord(
                organization_id=org_a.id,
                opportunity_id=opp_a.id,
                severity="high",
                alert_type="evidence_gap",
                title="A alert",
                message="A only",
                status="open",
                created_at=now,
            ),
            PursuitAlertRecord(
                organization_id=org_b.id,
                opportunity_id=opp_b.id,
                severity="high",
                alert_type="evidence_gap",
                title="B alert",
                message="B only",
                status="open",
                created_at=now,
            ),
            WatchItemRecord(
                organization_id=org_a.id,
                opportunity_id=opp_a.id,
                priority="high",
                status="active",
                owner="Alice",
                rationale="",
                next_review_at=now - timedelta(hours=1),
            ),
            WatchItemRecord(
                organization_id=org_b.id,
                opportunity_id=opp_b.id,
                priority="high",
                status="active",
                owner="Bob",
                rationale="",
                next_review_at=now - timedelta(hours=1),
            ),
        ])
        session.commit()

        org_a_id = org_a.id
        set_tenant_context(session, org_a_id)
        brief = daily_brief(session, window_hours=24, limit=10)

        assert brief["summary"]["pending_candidates"] == 1
        assert brief["summary"]["new_candidates"] == 1
        assert brief["summary"]["recent_events"] == 1
        assert brief["summary"]["open_alerts"] == 1
        assert brief["summary"]["overdue_actions"] == 1
        assert brief["summary"]["review_due"] == 1

        serialized = str(brief)
        assert "A Port Corridor" in serialized
        assert "A Candidate" in serialized
        assert "A overdue action" in serialized
        assert "A alert" in serialized
        assert "B Port Corridor" not in serialized
        assert "B Candidate" not in serialized
        assert "B overdue action" not in serialized
        assert "B alert" not in serialized

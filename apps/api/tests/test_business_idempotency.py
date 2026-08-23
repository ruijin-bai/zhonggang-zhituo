import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.business_idempotency import begin_operation, complete_operation
from app.db import (
    Base,
    IdempotencyRecord,
    OpportunityEventRecord,
    OpportunityRecord,
    OrganizationRecord,
    PursuitActionRecord,
    clear_tenant_context,
    set_tenant_context,
)
from app.tracking import complete_action


def _org(session: Session, code: str) -> OrganizationRecord:
    record = OrganizationRecord(
        id=str(uuid.uuid4()),
        name=f"Test {code} {uuid.uuid4().hex[:6]}",
        code=f"{code}-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    session.add(record)
    session.flush()
    return record


def _opportunity(opportunity_id: str, organization_id: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=organization_id,
        title="幂等测试项目",
        country="测试国",
        region="测试区域",
        sector="公路工程",
        stage="测试阶段",
        owner="测试业主",
        estimated_value_usd_m=None,
        summary="测试",
        score=50,
        grade="C",
        confidence=60,
        decision="CAUTION",
        breakdown={
            "strategic_fit": 10,
            "project_maturity": 8,
            "financing": 6,
            "client_quality": 6,
            "capability_fit": 10,
            "local_position": 4,
            "competition": 4,
            "risk_control": 2,
        },
        pursuit_thesis="测试",
        next_actions=[],
        is_demo=False,
    )


def test_same_key_and_payload_replays_completed_response() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = _org(session, "IDEM")
        session.commit()
        set_tenant_context(session, org.id)

        first = begin_operation(
            session,
            organization_id=org.id,
            scope="action.create:opp-1",
            raw_key="request-key-0001",
            request_payload={"title": "核实采购时间"},
        )
        assert first.is_replay is False
        complete_operation(session, first, {"ok": True, "action_id": 42})

        replay = begin_operation(
            session,
            organization_id=org.id,
            scope="action.create:opp-1",
            raw_key="request-key-0001",
            request_payload={"title": "核实采购时间"},
        )
        assert replay.is_replay is True
        assert replay.replay_payload == {"ok": True, "action_id": 42}


def test_same_key_with_different_payload_is_rejected() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = _org(session, "CONFLICT")
        session.commit()
        set_tenant_context(session, org.id)

        first = begin_operation(
            session,
            organization_id=org.id,
            scope="strategy.update:opp-1",
            raw_key="request-key-0002",
            request_payload={"win_theme": "A"},
        )
        complete_operation(session, first, {"ok": True})

        with pytest.raises(HTTPException) as exc:
            begin_operation(
                session,
                organization_id=org.id,
                scope="strategy.update:opp-1",
                raw_key="request-key-0002",
                request_payload={"win_theme": "B"},
            )
        assert exc.value.status_code == 409


def test_same_key_is_independent_across_organizations() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org_a = _org(session, "ORG-A")
        org_b = _org(session, "ORG-B")
        session.commit()

        set_tenant_context(session, org_a.id)
        first = begin_operation(
            session,
            organization_id=org_a.id,
            scope="watch:opp",
            raw_key="shared-key-0001",
            request_payload={"priority": "high"},
        )
        complete_operation(session, first, {"ok": True, "organization": "A"})

        clear_tenant_context(session)
        set_tenant_context(session, org_b.id)
        second = begin_operation(
            session,
            organization_id=org_b.id,
            scope="watch:opp",
            raw_key="shared-key-0001",
            request_payload={"priority": "high"},
        )
        assert second.is_replay is False
        complete_operation(session, second, {"ok": True, "organization": "B"})

        clear_tenant_context(session)
        count = session.scalar(select(func.count()).select_from(IdempotencyRecord))
        assert count == 2


def test_completing_action_twice_emits_one_completion_event() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = _org(session, "ACTION")
        opportunity_id = f"opp-{uuid.uuid4().hex[:8]}"
        session.add(_opportunity(opportunity_id, org.id))
        session.commit()
        set_tenant_context(session, org.id)

        action = PursuitActionRecord(
            opportunity_id=opportunity_id,
            title="测试行动",
            owner="测试人员",
            priority="high",
        )
        session.add(action)
        session.commit()

        first = complete_action(action.id, session)
        second = complete_action(action.id, session)
        assert first["already_completed"] is False
        assert second["already_completed"] is True

        count = session.scalar(
            select(func.count())
            .select_from(OpportunityEventRecord)
            .where(
                OpportunityEventRecord.opportunity_id == opportunity_id,
                OpportunityEventRecord.event_type == "action_completed",
            )
        )
        assert count == 1

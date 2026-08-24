from datetime import timedelta
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import (
    Base,
    MembershipRecord,
    OpportunityRecord,
    OrganizationRecord,
    UserRecord,
    clear_tenant_context,
    set_tenant_context,
    utc_now,
)
from app.pursuit_db import (
    PursuitDecisionRecord,
    PursuitParticipantRecord,
    PursuitWorkItemRecord,
    PursuitWorkspaceRecord,
)
from app.pursuit_service import (
    add_participant,
    create_work_item,
    ensure_workspace,
    my_work,
    open_gate,
    portfolio,
    record_gate_decision,
    request_gate_review,
    submit_gate_review,
    update_work_item,
    workspace_detail,
)
from app.security import Principal


def _org(session: Session, code: str) -> OrganizationRecord:
    row = OrganizationRecord(
        name=f"Org {code} {uuid.uuid4().hex[:6]}",
        code=f"{code}-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    session.add(row)
    session.flush()
    return row


def _member(session: Session, org: OrganizationRecord, name: str, role: str) -> tuple[UserRecord, MembershipRecord]:
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


def _principal(user: UserRecord, membership: MembershipRecord, org: OrganizationRecord) -> Principal:
    return Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=org.id,
        organization_name=org.name,
        role=membership.role,
    )


def _opportunity(opportunity_id: str, org_id: str, title: str) -> OpportunityRecord:
    return OpportunityRecord(
        id=opportunity_id,
        organization_id=org_id,
        title=title,
        country="Nigeria",
        region="West Africa",
        sector="Port",
        stage="Tender",
        owner="Test Owner",
        estimated_value_usd_m=100,
        summary="Pursuit orchestration test",
        score=70,
        grade="B",
        confidence=72,
        decision="WATCH",
        breakdown={
            "strategic_fit": 15,
            "project_maturity": 10,
            "financing": 10,
            "client_quality": 8,
            "capability_fit": 12,
            "local_position": 6,
            "competition": 6,
            "risk_control": 3,
        },
        pursuit_thesis="Test",
        next_actions=[],
        is_demo=False,
    )


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine, expire_on_commit=False)


def test_workspace_uses_real_membership_and_participants() -> None:
    engine, session = _session()
    org = _org(session, "PURS")
    manager_user, manager_membership = _member(session, org, "Manager", "manager")
    analyst_user, analyst_membership = _member(session, org, "Analyst", "analyst")
    opportunity_id = f"opp-{uuid.uuid4().hex[:8]}"
    session.add(_opportunity(opportunity_id, org.id, "Workspace Test"))
    session.commit()
    set_tenant_context(session, org.id)

    workspace = ensure_workspace(
        session,
        opportunity_id=opportunity_id,
        principal=_principal(manager_user, manager_membership, org),
        priority="high",
        rationale="重点经营",
    )
    add_participant(
        session,
        workspace_id=workspace.id,
        membership_id=analyst_membership.id,
        participant_role="contributor",
        responsibility="融资核实",
    )
    session.commit()

    detail = workspace_detail(session, opportunity_id)
    assert detail["lead"]["membership_id"] == manager_membership.id
    assert {item["member"]["membership_id"] for item in detail["participants"]} == {
        manager_membership.id,
        analyst_membership.id,
    }
    assert detail["priority"] == "high"

    session.close()
    engine.dispose()


def test_work_item_assignment_dependency_blocking_and_my_work() -> None:
    engine, session = _session()
    org = _org(session, "WORK")
    manager_user, manager_membership = _member(session, org, "Manager", "manager")
    analyst_user, analyst_membership = _member(session, org, "Analyst", "analyst")
    opportunity_id = f"opp-{uuid.uuid4().hex[:8]}"
    session.add(_opportunity(opportunity_id, org.id, "Work Test"))
    session.commit()
    set_tenant_context(session, org.id)
    manager = _principal(manager_user, manager_membership, org)
    analyst = _principal(analyst_user, analyst_membership, org)

    workspace = ensure_workspace(session, opportunity_id=opportunity_id, principal=manager)
    first = create_work_item(
        session,
        workspace_id=workspace.id,
        principal=manager,
        title="核实融资来源",
        assignee_membership_id=analyst_membership.id,
        due_at=utc_now() + timedelta(days=3),
    )
    second = create_work_item(
        session,
        workspace_id=workspace.id,
        principal=manager,
        title="形成融资判断",
        assignee_membership_id=analyst_membership.id,
        dependency_work_item_id=first.id,
    )

    with pytest.raises(ValueError, match="blocked_reason"):
        update_work_item(session, work_item_id=second.id, status="blocked")

    update_work_item(
        session,
        work_item_id=second.id,
        status="blocked",
        blocked_reason="等待融资机构正式回函",
    )
    session.commit()

    mine = my_work(session, analyst)
    assert {item["id"] for item in mine["work_items"]} == {first.id, second.id}
    blocked = next(item for item in mine["work_items"] if item["id"] == second.id)
    assert blocked["blocked_reason"] == "等待融资机构正式回函"

    update_work_item(session, work_item_id=first.id, status="done")
    session.commit()
    assert session.get(PursuitWorkItemRecord, first.id).completed_at is not None

    session.close()
    engine.dispose()


def test_dependency_cannot_cross_workspace() -> None:
    engine, session = _session()
    org = _org(session, "DEP")
    manager_user, manager_membership = _member(session, org, "Manager", "manager")
    session.add(_opportunity("dep-a", org.id, "A"))
    session.add(_opportunity("dep-b", org.id, "B"))
    session.commit()
    set_tenant_context(session, org.id)
    principal = _principal(manager_user, manager_membership, org)
    workspace_a = ensure_workspace(session, opportunity_id="dep-a", principal=principal)
    workspace_b = ensure_workspace(session, opportunity_id="dep-b", principal=principal)
    item_a = create_work_item(session, workspace_id=workspace_a.id, principal=principal, title="A task")

    with pytest.raises(ValueError, match="same pursuit workspace"):
        create_work_item(
            session,
            workspace_id=workspace_b.id,
            principal=principal,
            title="B task",
            dependency_work_item_id=item_a.id,
        )

    session.close()
    engine.dispose()


def test_go_requires_review_and_decisions_keep_lineage() -> None:
    engine, session = _session()
    org = _org(session, "GATE")
    manager_user, manager_membership = _member(session, org, "Manager", "manager")
    reviewer_user, reviewer_membership = _member(session, org, "Reviewer", "analyst")
    opportunity_id = f"opp-{uuid.uuid4().hex[:8]}"
    session.add(_opportunity(opportunity_id, org.id, "Gate Test"))
    session.commit()
    set_tenant_context(session, org.id)
    manager = _principal(manager_user, manager_membership, org)
    reviewer = _principal(reviewer_user, reviewer_membership, org)
    workspace = ensure_workspace(session, opportunity_id=opportunity_id, principal=manager)
    gate = open_gate(
        session,
        workspace_id=workspace.id,
        principal=manager,
        gate_type="bid",
        title="是否正式投标",
        due_at=None,
    )
    review = request_gate_review(
        session,
        gate_id=gate.id,
        reviewer_membership_id=reviewer_membership.id,
        principal=manager,
    )

    with pytest.raises(ValueError, match="reviews"):
        record_gate_decision(
            session,
            gate_id=gate.id,
            decision="GO",
            rationale="投入投标",
            principal=manager,
        )

    submit_gate_review(
        session,
        review_id=review.id,
        status="approved",
        note="关键条件已核实",
        principal=reviewer,
    )
    first = record_gate_decision(
        session,
        gate_id=gate.id,
        decision="GO",
        rationale="进入正式投标",
        principal=manager,
    )
    second = record_gate_decision(
        session,
        gate_id=gate.id,
        decision="HOLD",
        rationale="采购时间表发生变化，暂缓投入",
        principal=manager,
    )
    session.commit()

    assert second.supersedes_decision_id == first.id
    assert session.scalar(select(PursuitDecisionRecord).where(PursuitDecisionRecord.id == second.id)) is not None

    session.close()
    engine.dispose()


def test_pursuit_models_are_tenant_isolated() -> None:
    engine, session = _session()
    org_a = _org(session, "TEN-A")
    org_b = _org(session, "TEN-B")
    user_a, membership_a = _member(session, org_a, "A Manager", "manager")
    user_b, membership_b = _member(session, org_b, "B Manager", "manager")
    session.add(_opportunity("tenant-a-opp", org_a.id, "A Opportunity"))
    session.add(_opportunity("tenant-b-opp", org_b.id, "B Opportunity"))
    session.commit()

    set_tenant_context(session, org_a.id)
    ensure_workspace(
        session,
        opportunity_id="tenant-a-opp",
        principal=_principal(user_a, membership_a, org_a),
    )
    session.commit()

    clear_tenant_context(session)
    set_tenant_context(session, org_b.id)
    ensure_workspace(
        session,
        opportunity_id="tenant-b-opp",
        principal=_principal(user_b, membership_b, org_b),
    )
    session.commit()

    rows_b = session.scalars(select(PursuitWorkspaceRecord)).all()
    assert [row.opportunity_id for row in rows_b] == ["tenant-b-opp"]
    assert portfolio(session)["items"][0]["opportunity_id"] == "tenant-b-opp"

    clear_tenant_context(session)
    set_tenant_context(session, org_a.id)
    rows_a = session.scalars(select(PursuitWorkspaceRecord)).all()
    assert [row.opportunity_id for row in rows_a] == ["tenant-a-opp"]
    participants = session.scalars(select(PursuitParticipantRecord)).all()
    assert all(item.organization_id == org_a.id for item in participants)

    session.close()
    engine.dispose()

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import MembershipRecord, OpportunityEventRecord, OpportunityRecord, UserRecord, utc_now
from .pursuit_db import (
    PursuitDecisionGateRecord,
    PursuitDecisionRecord,
    PursuitGateReviewRecord,
    PursuitParticipantRecord,
    PursuitWorkItemRecord,
    PursuitWorkspaceRecord,
)
from .security import ROLE_LEVEL, Principal

VALID_PARTICIPANT_ROLES = {"lead", "contributor", "reviewer", "watcher"}
VALID_WORK_STATUSES = {"open", "in_progress", "blocked", "done", "cancelled"}
VALID_WORK_TYPES = {"action", "milestone", "request"}
VALID_GATE_TYPES = {"qualification", "pursuit", "bid", "submission", "closeout"}
VALID_REVIEW_STATUSES = {"approved", "changes_requested", "waived"}
VALID_DECISIONS = {"GO", "HOLD", "NO_GO"}


def principal_membership(session: Session, principal: Principal) -> MembershipRecord:
    membership = session.scalar(
        select(MembershipRecord).where(
            MembershipRecord.organization_id == principal.organization_id,
            MembershipRecord.user_id == principal.user_id,
            MembershipRecord.is_active.is_(True),
        )
    )
    if membership is None:
        raise ValueError("current user has no active membership in this organization")
    return membership


def _membership(session: Session, organization_id: str, membership_id: int) -> MembershipRecord:
    membership = session.scalar(
        select(MembershipRecord).where(
            MembershipRecord.id == membership_id,
            MembershipRecord.organization_id == organization_id,
            MembershipRecord.is_active.is_(True),
        )
    )
    if membership is None:
        raise ValueError("membership is not active in the current organization")
    return membership


def _membership_map(session: Session, membership_ids: set[int]) -> dict[int, dict]:
    if not membership_ids:
        return {}
    rows = session.execute(
        select(MembershipRecord, UserRecord)
        .join(UserRecord, UserRecord.id == MembershipRecord.user_id)
        .where(MembershipRecord.id.in_(membership_ids))
    ).all()
    return {
        membership.id: {
            "membership_id": membership.id,
            "user_id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "role": membership.role,
            "active": membership.is_active and user.is_active,
        }
        for membership, user in rows
    }


def _opportunity(session: Session, opportunity_id: str) -> OpportunityRecord:
    row = session.get(OpportunityRecord, opportunity_id)
    if row is None:
        raise ValueError("opportunity not found")
    return row


def _workspace(session: Session, workspace_id: str) -> PursuitWorkspaceRecord:
    row = session.get(PursuitWorkspaceRecord, workspace_id)
    if row is None:
        raise ValueError("pursuit workspace not found")
    return row


def _workspace_for_opportunity(session: Session, opportunity_id: str) -> PursuitWorkspaceRecord:
    row = session.scalar(
        select(PursuitWorkspaceRecord).where(PursuitWorkspaceRecord.opportunity_id == opportunity_id)
    )
    if row is None:
        raise ValueError("pursuit workspace not found")
    return row


def _ensure_participant(
    session: Session,
    *,
    workspace: PursuitWorkspaceRecord,
    membership_id: int,
    participant_role: str,
    responsibility: str = "",
) -> PursuitParticipantRecord:
    row = session.scalar(
        select(PursuitParticipantRecord).where(
            PursuitParticipantRecord.workspace_id == workspace.id,
            PursuitParticipantRecord.membership_id == membership_id,
        )
    )
    if row is None:
        row = PursuitParticipantRecord(
            workspace_id=workspace.id,
            membership_id=membership_id,
            participant_role=participant_role,
            responsibility=responsibility,
            status="active",
        )
        session.add(row)
    else:
        row.participant_role = participant_role
        row.responsibility = responsibility
        row.status = "active"
        row.updated_at = utc_now()
    session.flush()
    return row


def ensure_workspace(
    session: Session,
    *,
    opportunity_id: str,
    principal: Principal,
    priority: str = "medium",
    rationale: str = "",
    next_review_at: datetime | None = None,
) -> PursuitWorkspaceRecord:
    _opportunity(session, opportunity_id)
    membership = principal_membership(session, principal)
    row = session.scalar(
        select(PursuitWorkspaceRecord).where(PursuitWorkspaceRecord.opportunity_id == opportunity_id)
    )
    if row is None:
        row = PursuitWorkspaceRecord(
            id=str(uuid4()),
            opportunity_id=opportunity_id,
            status="active",
            priority=priority,
            lead_membership_id=membership.id,
            created_by_membership_id=membership.id,
            rationale=rationale,
            next_review_at=next_review_at,
        )
        session.add(row)
        session.flush()
    else:
        row.status = "active"
        row.priority = priority or row.priority
        if rationale:
            row.rationale = rationale
        if next_review_at is not None:
            row.next_review_at = next_review_at
        if row.lead_membership_id is None:
            row.lead_membership_id = membership.id
        row.updated_at = utc_now()
    _ensure_participant(
        session,
        workspace=row,
        membership_id=row.lead_membership_id or membership.id,
        participant_role="lead",
        responsibility="经营牵头",
    )
    session.flush()
    return row


def add_participant(
    session: Session,
    *,
    workspace_id: str,
    membership_id: int,
    participant_role: str,
    responsibility: str,
) -> PursuitParticipantRecord:
    if participant_role not in VALID_PARTICIPANT_ROLES:
        raise ValueError("unsupported participant role")
    workspace = _workspace(session, workspace_id)
    _membership(session, workspace.organization_id, membership_id)
    participant = _ensure_participant(
        session,
        workspace=workspace,
        membership_id=membership_id,
        participant_role=participant_role,
        responsibility=responsibility,
    )
    if participant_role == "lead":
        old_leads = session.scalars(
            select(PursuitParticipantRecord).where(
                PursuitParticipantRecord.workspace_id == workspace.id,
                PursuitParticipantRecord.participant_role == "lead",
                PursuitParticipantRecord.membership_id != membership_id,
            )
        ).all()
        for item in old_leads:
            item.participant_role = "contributor"
            item.updated_at = utc_now()
        workspace.lead_membership_id = membership_id
        workspace.updated_at = utc_now()
    session.flush()
    return participant


def create_work_item(
    session: Session,
    *,
    workspace_id: str,
    principal: Principal,
    title: str,
    description: str = "",
    work_type: str = "action",
    assignee_membership_id: int | None = None,
    priority: str = "medium",
    due_at: datetime | None = None,
    dependency_work_item_id: str | None = None,
) -> PursuitWorkItemRecord:
    if work_type not in VALID_WORK_TYPES:
        raise ValueError("unsupported work item type")
    workspace = _workspace(session, workspace_id)
    creator = principal_membership(session, principal)
    if assignee_membership_id is not None:
        _membership(session, workspace.organization_id, assignee_membership_id)
    if dependency_work_item_id:
        dependency = session.get(PursuitWorkItemRecord, dependency_work_item_id)
        if dependency is None or dependency.workspace_id != workspace.id:
            raise ValueError("dependency must belong to the same pursuit workspace")
    row = PursuitWorkItemRecord(
        id=str(uuid4()),
        workspace_id=workspace.id,
        opportunity_id=workspace.opportunity_id,
        work_type=work_type,
        title=title.strip(),
        description=description.strip(),
        assignee_membership_id=assignee_membership_id,
        created_by_membership_id=creator.id,
        status="open",
        priority=priority,
        due_at=due_at,
        dependency_work_item_id=dependency_work_item_id,
    )
    session.add(row)
    session.flush()
    return row


def update_work_item(
    session: Session,
    *,
    work_item_id: str,
    title: str | None = None,
    description: str | None = None,
    assignee_membership_id: int | None = None,
    clear_assignee: bool = False,
    status: str | None = None,
    priority: str | None = None,
    due_at: datetime | None = None,
    clear_due_at: bool = False,
    blocked_reason: str | None = None,
    dependency_work_item_id: str | None = None,
    clear_dependency: bool = False,
) -> PursuitWorkItemRecord:
    row = session.get(PursuitWorkItemRecord, work_item_id)
    if row is None:
        raise ValueError("work item not found")
    if status is not None and status not in VALID_WORK_STATUSES:
        raise ValueError("unsupported work item status")
    if assignee_membership_id is not None:
        _membership(session, row.organization_id, assignee_membership_id)
        row.assignee_membership_id = assignee_membership_id
    elif clear_assignee:
        row.assignee_membership_id = None
    if dependency_work_item_id is not None:
        if dependency_work_item_id == row.id:
            raise ValueError("work item cannot depend on itself")
        dependency = session.get(PursuitWorkItemRecord, dependency_work_item_id)
        if dependency is None or dependency.workspace_id != row.workspace_id:
            raise ValueError("dependency must belong to the same pursuit workspace")
        row.dependency_work_item_id = dependency_work_item_id
    elif clear_dependency:
        row.dependency_work_item_id = None
    if title is not None:
        row.title = title.strip()
    if description is not None:
        row.description = description.strip()
    if priority is not None:
        row.priority = priority
    if due_at is not None:
        row.due_at = due_at
    elif clear_due_at:
        row.due_at = None
    if blocked_reason is not None:
        row.blocked_reason = blocked_reason.strip() or None
    if status is not None:
        if status == "blocked" and not (row.blocked_reason or "").strip():
            raise ValueError("blocked work item requires blocked_reason")
        row.status = status
        if status == "done":
            row.completed_at = row.completed_at or utc_now()
            row.blocked_reason = None
        elif status in {"open", "in_progress"}:
            row.completed_at = None
            if status != "blocked":
                row.blocked_reason = None
        elif status == "cancelled":
            row.completed_at = None
    row.updated_at = utc_now()
    session.flush()
    return row


def open_gate(
    session: Session,
    *,
    workspace_id: str,
    principal: Principal,
    gate_type: str,
    title: str,
    due_at: datetime | None,
) -> PursuitDecisionGateRecord:
    if gate_type not in VALID_GATE_TYPES:
        raise ValueError("unsupported decision gate type")
    workspace = _workspace(session, workspace_id)
    membership = principal_membership(session, principal)
    row = PursuitDecisionGateRecord(
        id=str(uuid4()),
        workspace_id=workspace.id,
        opportunity_id=workspace.opportunity_id,
        gate_type=gate_type,
        title=title.strip(),
        status="open",
        due_at=due_at,
        opened_by_membership_id=membership.id,
    )
    session.add(row)
    session.flush()
    return row


def request_gate_review(
    session: Session,
    *,
    gate_id: str,
    reviewer_membership_id: int,
    principal: Principal,
) -> PursuitGateReviewRecord:
    gate = session.get(PursuitDecisionGateRecord, gate_id)
    if gate is None:
        raise ValueError("decision gate not found")
    if gate.status == "cancelled":
        raise ValueError("cancelled gate cannot request review")
    _membership(session, gate.organization_id, reviewer_membership_id)
    requester = principal_membership(session, principal)
    row = session.scalar(
        select(PursuitGateReviewRecord).where(
            PursuitGateReviewRecord.gate_id == gate.id,
            PursuitGateReviewRecord.reviewer_membership_id == reviewer_membership_id,
        )
    )
    if row is None:
        row = PursuitGateReviewRecord(
            id=str(uuid4()),
            gate_id=gate.id,
            reviewer_membership_id=reviewer_membership_id,
            requested_by_membership_id=requester.id,
            status="pending",
        )
        session.add(row)
    else:
        row.requested_by_membership_id = requester.id
        row.status = "pending"
        row.note = ""
        row.requested_at = utc_now()
        row.reviewed_at = None
    session.flush()
    return row


def submit_gate_review(
    session: Session,
    *,
    review_id: str,
    status: str,
    note: str,
    principal: Principal,
) -> PursuitGateReviewRecord:
    if status not in VALID_REVIEW_STATUSES:
        raise ValueError("unsupported review status")
    row = session.get(PursuitGateReviewRecord, review_id)
    if row is None:
        raise ValueError("gate review not found")
    current = principal_membership(session, principal)
    if current.id != row.reviewer_membership_id and ROLE_LEVEL[principal.role] < ROLE_LEVEL["manager"]:
        raise PermissionError("only the assigned reviewer or a manager may submit this review")
    row.status = status
    row.note = note.strip()
    row.reviewed_at = utc_now()
    session.flush()
    return row


def record_gate_decision(
    session: Session,
    *,
    gate_id: str,
    decision: str,
    rationale: str,
    principal: Principal,
) -> PursuitDecisionRecord:
    if decision not in VALID_DECISIONS:
        raise ValueError("unsupported pursuit decision")
    gate = session.get(PursuitDecisionGateRecord, gate_id)
    if gate is None:
        raise ValueError("decision gate not found")
    if gate.status == "cancelled":
        raise ValueError("cancelled gate cannot be decided")
    if decision == "GO":
        reviews = session.scalars(
            select(PursuitGateReviewRecord).where(PursuitGateReviewRecord.gate_id == gate.id)
        ).all()
        if any(item.status == "pending" for item in reviews):
            raise ValueError("GO decision requires all requested reviews to be resolved")
        if any(item.status == "changes_requested" for item in reviews):
            raise ValueError("GO decision is blocked by a changes_requested review")
    membership = principal_membership(session, principal)
    previous = session.scalar(
        select(PursuitDecisionRecord)
        .where(PursuitDecisionRecord.gate_id == gate.id)
        .order_by(PursuitDecisionRecord.decided_at.desc())
        .limit(1)
    )
    row = PursuitDecisionRecord(
        id=str(uuid4()),
        gate_id=gate.id,
        opportunity_id=gate.opportunity_id,
        decision=decision,
        rationale=rationale.strip(),
        decided_by_membership_id=membership.id,
        supersedes_decision_id=previous.id if previous else None,
    )
    session.add(row)
    if decision == "HOLD":
        gate.status = "open"
        gate.closed_at = None
    else:
        gate.status = "decided"
        gate.closed_at = utc_now()
    session.flush()
    return row


def _workspace_payload(session: Session, workspace: PursuitWorkspaceRecord) -> dict:
    opportunity = _opportunity(session, workspace.opportunity_id)
    participants = session.scalars(
        select(PursuitParticipantRecord)
        .where(PursuitParticipantRecord.workspace_id == workspace.id)
        .order_by(PursuitParticipantRecord.participant_role.asc(), PursuitParticipantRecord.created_at.asc())
    ).all()
    items = session.scalars(
        select(PursuitWorkItemRecord)
        .where(PursuitWorkItemRecord.workspace_id == workspace.id)
        .order_by(PursuitWorkItemRecord.created_at.desc())
    ).all()
    gates = session.scalars(
        select(PursuitDecisionGateRecord)
        .where(PursuitDecisionGateRecord.workspace_id == workspace.id)
        .order_by(PursuitDecisionGateRecord.opened_at.desc())
    ).all()
    reviews = session.scalars(
        select(PursuitGateReviewRecord).where(
            PursuitGateReviewRecord.gate_id.in_([gate.id for gate in gates])
        )
    ).all() if gates else []
    decisions = session.scalars(
        select(PursuitDecisionRecord)
        .where(PursuitDecisionRecord.gate_id.in_([gate.id for gate in gates]))
        .order_by(PursuitDecisionRecord.decided_at.asc())
    ).all() if gates else []
    membership_ids = {
        *(item.membership_id for item in participants),
        *(item.assignee_membership_id for item in items if item.assignee_membership_id is not None),
        *(item.created_by_membership_id for item in items if item.created_by_membership_id is not None),
        *(item.reviewer_membership_id for item in reviews),
        *(item.requested_by_membership_id for item in reviews if item.requested_by_membership_id is not None),
        *(item.decided_by_membership_id for item in decisions),
    }
    if workspace.lead_membership_id is not None:
        membership_ids.add(workspace.lead_membership_id)
    members = _membership_map(session, membership_ids)
    reviews_by_gate: dict[str, list[dict]] = {}
    for review in reviews:
        reviews_by_gate.setdefault(review.gate_id, []).append(
            {
                "id": review.id,
                "reviewer": members.get(review.reviewer_membership_id),
                "status": review.status,
                "note": review.note,
                "requested_at": review.requested_at.isoformat(),
                "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
            }
        )
    decisions_by_gate: dict[str, list[dict]] = {}
    for decision in decisions:
        decisions_by_gate.setdefault(decision.gate_id, []).append(
            {
                "id": decision.id,
                "decision": decision.decision,
                "rationale": decision.rationale,
                "decided_by": members.get(decision.decided_by_membership_id),
                "supersedes_decision_id": decision.supersedes_decision_id,
                "decided_at": decision.decided_at.isoformat(),
            }
        )
    return {
        "id": workspace.id,
        "status": workspace.status,
        "priority": workspace.priority,
        "rationale": workspace.rationale,
        "next_review_at": workspace.next_review_at.isoformat() if workspace.next_review_at else None,
        "lead": members.get(workspace.lead_membership_id) if workspace.lead_membership_id else None,
        "opportunity": {
            "id": opportunity.id,
            "title": opportunity.title,
            "country": opportunity.country,
            "sector": opportunity.sector,
            "stage": opportunity.stage,
            "score": opportunity.score,
            "grade": opportunity.grade,
            "confidence": opportunity.confidence,
            "decision": opportunity.decision,
        },
        "participants": [
            {
                "id": item.id,
                "member": members.get(item.membership_id),
                "participant_role": item.participant_role,
                "responsibility": item.responsibility,
                "status": item.status,
            }
            for item in participants
        ],
        "work_items": [
            {
                "id": item.id,
                "work_type": item.work_type,
                "title": item.title,
                "description": item.description,
                "assignee": members.get(item.assignee_membership_id) if item.assignee_membership_id else None,
                "legacy_owner_text": item.legacy_owner_text,
                "status": item.status,
                "priority": item.priority,
                "due_at": item.due_at.isoformat() if item.due_at else None,
                "blocked_reason": item.blocked_reason,
                "dependency_work_item_id": item.dependency_work_item_id,
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in items
        ],
        "gates": [
            {
                "id": gate.id,
                "gate_type": gate.gate_type,
                "title": gate.title,
                "status": gate.status,
                "due_at": gate.due_at.isoformat() if gate.due_at else None,
                "opened_at": gate.opened_at.isoformat(),
                "closed_at": gate.closed_at.isoformat() if gate.closed_at else None,
                "reviews": reviews_by_gate.get(gate.id, []),
                "decisions": decisions_by_gate.get(gate.id, []),
            }
            for gate in gates
        ],
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
    }


def workspace_detail(session: Session, opportunity_id: str) -> dict:
    return _workspace_payload(session, _workspace_for_opportunity(session, opportunity_id))


def my_work(session: Session, principal: Principal) -> dict:
    membership = principal_membership(session, principal)
    items = session.scalars(
        select(PursuitWorkItemRecord)
        .where(
            PursuitWorkItemRecord.assignee_membership_id == membership.id,
            PursuitWorkItemRecord.status.in_(["open", "in_progress", "blocked"]),
        )
        .order_by(PursuitWorkItemRecord.due_at.asc().nullslast(), PursuitWorkItemRecord.priority.asc())
    ).all()
    reviews = session.scalars(
        select(PursuitGateReviewRecord)
        .where(
            PursuitGateReviewRecord.reviewer_membership_id == membership.id,
            PursuitGateReviewRecord.status == "pending",
        )
        .order_by(PursuitGateReviewRecord.requested_at.asc())
    ).all()
    participants = session.scalars(
        select(PursuitParticipantRecord).where(
            PursuitParticipantRecord.membership_id == membership.id,
            PursuitParticipantRecord.status == "active",
        )
    ).all()
    workspace_ids = {item.workspace_id for item in items} | {item.workspace_id for item in participants}
    gate_ids = {review.gate_id for review in reviews}
    gates = {
        gate.id: gate
        for gate in session.scalars(
            select(PursuitDecisionGateRecord).where(PursuitDecisionGateRecord.id.in_(gate_ids))
        ).all()
    } if gate_ids else {}
    workspace_ids |= {gate.workspace_id for gate in gates.values()}
    workspaces = {
        row.id: row
        for row in session.scalars(
            select(PursuitWorkspaceRecord).where(PursuitWorkspaceRecord.id.in_(workspace_ids))
        ).all()
    } if workspace_ids else {}
    opportunity_ids = {row.opportunity_id for row in workspaces.values()}
    opportunities = {
        row.id: row
        for row in session.scalars(
            select(OpportunityRecord).where(OpportunityRecord.id.in_(opportunity_ids))
        ).all()
    } if opportunity_ids else {}

    def context(workspace_id: str) -> dict:
        workspace = workspaces.get(workspace_id)
        opportunity = opportunities.get(workspace.opportunity_id) if workspace else None
        return {
            "workspace_id": workspace_id,
            "opportunity_id": opportunity.id if opportunity else None,
            "opportunity_title": opportunity.title if opportunity else "",
            "country": opportunity.country if opportunity else "",
        }

    return {
        "membership": _membership_map(session, {membership.id}).get(membership.id),
        "work_items": [
            {
                **context(item.workspace_id),
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "priority": item.priority,
                "due_at": item.due_at.isoformat() if item.due_at else None,
                "blocked_reason": item.blocked_reason,
            }
            for item in items
        ],
        "pending_reviews": [
            {
                **context(gates[item.gate_id].workspace_id),
                "review_id": item.id,
                "gate_id": item.gate_id,
                "gate_title": gates[item.gate_id].title,
                "requested_at": item.requested_at.isoformat(),
            }
            for item in reviews
            if item.gate_id in gates
        ],
        "workspace_count": len({item.workspace_id for item in participants}),
    }


def team_work(session: Session) -> dict:
    workspaces = session.scalars(
        select(PursuitWorkspaceRecord)
        .where(PursuitWorkspaceRecord.status.in_(["active", "hold"]))
        .order_by(PursuitWorkspaceRecord.updated_at.desc())
    ).all()
    rows: list[dict] = []
    for workspace in workspaces:
        counts = dict(
            session.execute(
                select(PursuitWorkItemRecord.status, func.count())
                .where(PursuitWorkItemRecord.workspace_id == workspace.id)
                .group_by(PursuitWorkItemRecord.status)
            ).all()
        )
        participant_count = session.scalar(
            select(func.count())
            .select_from(PursuitParticipantRecord)
            .where(
                PursuitParticipantRecord.workspace_id == workspace.id,
                PursuitParticipantRecord.status == "active",
            )
        ) or 0
        opportunity = _opportunity(session, workspace.opportunity_id)
        rows.append(
            {
                "workspace_id": workspace.id,
                "opportunity_id": opportunity.id,
                "title": opportunity.title,
                "country": opportunity.country,
                "sector": opportunity.sector,
                "priority": workspace.priority,
                "participant_count": participant_count,
                "open": counts.get("open", 0),
                "in_progress": counts.get("in_progress", 0),
                "blocked": counts.get("blocked", 0),
                "done": counts.get("done", 0),
                "next_review_at": workspace.next_review_at.isoformat() if workspace.next_review_at else None,
            }
        )
    return {"count": len(rows), "workspaces": rows}


def portfolio(session: Session) -> dict:
    workspaces = session.scalars(
        select(PursuitWorkspaceRecord).order_by(PursuitWorkspaceRecord.updated_at.desc())
    ).all()
    rows: list[dict] = []
    for workspace in workspaces:
        opportunity = _opportunity(session, workspace.opportunity_id)
        open_count = session.scalar(
            select(func.count())
            .select_from(PursuitWorkItemRecord)
            .where(
                PursuitWorkItemRecord.workspace_id == workspace.id,
                PursuitWorkItemRecord.status.in_(["open", "in_progress", "blocked"]),
            )
        ) or 0
        blocked_count = session.scalar(
            select(func.count())
            .select_from(PursuitWorkItemRecord)
            .where(
                PursuitWorkItemRecord.workspace_id == workspace.id,
                PursuitWorkItemRecord.status == "blocked",
            )
        ) or 0
        latest_gate = session.scalar(
            select(PursuitDecisionGateRecord)
            .where(PursuitDecisionGateRecord.workspace_id == workspace.id)
            .order_by(PursuitDecisionGateRecord.opened_at.desc())
            .limit(1)
        )
        latest_decision = None
        if latest_gate is not None:
            latest_decision = session.scalar(
                select(PursuitDecisionRecord)
                .where(PursuitDecisionRecord.gate_id == latest_gate.id)
                .order_by(PursuitDecisionRecord.decided_at.desc())
                .limit(1)
            )
        rows.append(
            {
                "workspace_id": workspace.id,
                "opportunity_id": opportunity.id,
                "title": opportunity.title,
                "country": opportunity.country,
                "sector": opportunity.sector,
                "stage": opportunity.stage,
                "workspace_status": workspace.status,
                "priority": workspace.priority,
                "score": opportunity.score,
                "grade": opportunity.grade,
                "confidence": opportunity.confidence,
                "assessment_decision": opportunity.decision,
                "open_work_items": open_count,
                "blocked_work_items": blocked_count,
                "gate": (
                    {
                        "id": latest_gate.id,
                        "type": latest_gate.gate_type,
                        "title": latest_gate.title,
                        "status": latest_gate.status,
                        "decision": latest_decision.decision if latest_decision else None,
                    }
                    if latest_gate
                    else None
                ),
            }
        )
    return {"count": len(rows), "items": rows}


def emit_pursuit_event(session: Session, *, opportunity_id: str, event_type: str, payload: dict) -> None:
    session.add(
        OpportunityEventRecord(
            opportunity_id=opportunity_id,
            event_type=event_type,
            payload=payload,
        )
    )

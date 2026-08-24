from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import OpportunityRecord, utc_now
from .pursuit_db import (
    PursuitDecisionGateRecord,
    PursuitGateReviewRecord,
    PursuitWorkItemRecord,
    PursuitWorkspaceRecord,
)
from .pursuit_reminder_db import PursuitReminderRecord
from .pursuit_service import principal_membership
from .security import Principal, ROLE_LEVEL


ACTIVE_WORK_STATUSES = {"open", "in_progress", "blocked"}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _dedupe_key(reminder_type: str, resource_id: str, recipient_membership_id: int) -> str:
    return f"{reminder_type}:{resource_id}:{recipient_membership_id}"[:160]


def _ensure_reminder(
    session: Session,
    *,
    active_keys: set[str],
    workspace: PursuitWorkspaceRecord,
    recipient_membership_id: int,
    reminder_type: str,
    severity: str,
    title: str,
    message: str,
    work_item_id: str | None = None,
    gate_id: str | None = None,
    review_id: str | None = None,
    source_due_at: datetime | None = None,
    escalated_to_membership_id: int | None = None,
    escalation_level: int = 0,
    now: datetime,
) -> PursuitReminderRecord:
    resource_id = work_item_id or review_id or gate_id or workspace.id
    key = _dedupe_key(reminder_type, resource_id, recipient_membership_id)
    active_keys.add(key)
    row = session.scalar(
        select(PursuitReminderRecord).where(PursuitReminderRecord.dedupe_key == key)
    )
    if row is None:
        row = PursuitReminderRecord(
            id=str(uuid4()),
            workspace_id=workspace.id,
            opportunity_id=workspace.opportunity_id,
            recipient_membership_id=recipient_membership_id,
            escalated_to_membership_id=escalated_to_membership_id,
            work_item_id=work_item_id,
            gate_id=gate_id,
            review_id=review_id,
            reminder_type=reminder_type,
            severity=severity,
            status="open",
            title=title,
            message=message,
            dedupe_key=key,
            source_due_at=source_due_at,
            escalation_level=escalation_level,
            first_triggered_at=now,
            last_triggered_at=now,
            last_evaluated_at=now,
            occurrence_count=1,
        )
        session.add(row)
    else:
        previous_escalation_level = row.escalation_level
        if row.status == "resolved":
            row.status = "open"
            row.resolved_at = None
            row.acknowledged_at = None
            row.occurrence_count += 1
            row.last_triggered_at = now
        elif escalation_level > previous_escalation_level and row.status == "acknowledged":
            # Acknowledgement means the original recipient saw the condition; it does not
            # acknowledge a later escalation to the workspace lead. Re-open the same durable
            # reminder without counting a new occurrence of the underlying business condition.
            row.status = "open"
            row.acknowledged_at = None
            row.last_triggered_at = now
        row.workspace_id = workspace.id
        row.opportunity_id = workspace.opportunity_id
        row.recipient_membership_id = recipient_membership_id
        row.escalated_to_membership_id = escalated_to_membership_id
        row.work_item_id = work_item_id
        row.gate_id = gate_id
        row.review_id = review_id
        row.reminder_type = reminder_type
        row.severity = severity
        row.title = title
        row.message = message
        row.source_due_at = source_due_at
        row.escalation_level = escalation_level
        row.last_evaluated_at = now
    return row


def _resolve_inactive(session: Session, active_keys: set[str], now: datetime) -> int:
    active_rows = session.scalars(
        select(PursuitReminderRecord).where(PursuitReminderRecord.status != "resolved")
    ).all()
    resolved = 0
    for row in active_rows:
        if row.dedupe_key in active_keys:
            continue
        row.status = "resolved"
        row.resolved_at = now
        row.last_evaluated_at = now
        resolved += 1
    return resolved


def reconcile_pursuit_reminders(session: Session, *, now: datetime | None = None) -> dict:
    """Reconcile durable reminder facts for one tenant.

    This function is deterministic for the same database state and clock. It does not send email
    or chat messages; external delivery channels can consume these persisted reminder facts later.
    """

    settings = get_settings()
    now = _as_utc(now or utc_now())
    due_soon_until = now + timedelta(hours=settings.pursuit_due_soon_hours)
    active_keys: set[str] = set()
    touched = 0
    escalated = 0

    workspaces = session.scalars(
        select(PursuitWorkspaceRecord).where(PursuitWorkspaceRecord.status == "active")
    ).all()
    workspace_by_id = {row.id: row for row in workspaces}

    for workspace in workspaces:
        if workspace.next_review_at and _as_utc(workspace.next_review_at) <= now and workspace.lead_membership_id:
            _ensure_reminder(
                session,
                active_keys=active_keys,
                workspace=workspace,
                recipient_membership_id=workspace.lead_membership_id,
                reminder_type="workspace_review_due",
                severity="warning",
                title="Pursuit Workspace 复盘已到期",
                message="重点经营项目已到计划复盘时间，请更新执行状态、关键证据和下一步投入。",
                source_due_at=workspace.next_review_at,
                now=now,
            )
            touched += 1

    work_items = session.scalars(
        select(PursuitWorkItemRecord).where(PursuitWorkItemRecord.status.in_(ACTIVE_WORK_STATUSES))
    ).all()
    for item in work_items:
        workspace = workspace_by_id.get(item.workspace_id)
        if workspace is None:
            continue
        recipient = item.assignee_membership_id or workspace.lead_membership_id
        if recipient is None:
            continue
        lead = workspace.lead_membership_id

        if item.due_at:
            due_at = _as_utc(item.due_at)
            if due_at <= now:
                overdue_hours = (now - due_at).total_seconds() / 3600
                should_escalate = (
                    overdue_hours >= settings.pursuit_overdue_escalation_hours
                    and lead is not None
                    and lead != recipient
                )
                _ensure_reminder(
                    session,
                    active_keys=active_keys,
                    workspace=workspace,
                    recipient_membership_id=recipient,
                    escalated_to_membership_id=lead if should_escalate else None,
                    escalation_level=1 if should_escalate else 0,
                    reminder_type="work_overdue",
                    severity="critical" if should_escalate else "high",
                    title=f"经营工作已逾期：{item.title}",
                    message=(
                        f"Work Item 已逾期约 {int(overdue_hours)} 小时。"
                        + ("已升级给 Pursuit Lead。" if should_escalate else "请更新状态或完成时间。")
                    ),
                    work_item_id=item.id,
                    source_due_at=item.due_at,
                    now=now,
                )
                touched += 1
                escalated += int(should_escalate)
            elif due_at <= due_soon_until:
                remaining_hours = max(0, int((due_at - now).total_seconds() / 3600))
                _ensure_reminder(
                    session,
                    active_keys=active_keys,
                    workspace=workspace,
                    recipient_membership_id=recipient,
                    reminder_type="work_due_soon",
                    severity="warning",
                    title=f"经营工作临近截止：{item.title}",
                    message=f"Work Item 距截止时间约 {remaining_hours} 小时，请确认交付路径和依赖是否清晰。",
                    work_item_id=item.id,
                    source_due_at=item.due_at,
                    now=now,
                )
                touched += 1

        if item.status == "blocked":
            blocked_since = _as_utc(item.blocked_since or item.updated_at)
            blocked_hours = (now - blocked_since).total_seconds() / 3600
            should_escalate = (
                blocked_hours >= settings.pursuit_blocked_escalation_hours
                and lead is not None
                and lead != recipient
            )
            _ensure_reminder(
                session,
                active_keys=active_keys,
                workspace=workspace,
                recipient_membership_id=recipient,
                escalated_to_membership_id=lead if should_escalate else None,
                escalation_level=1 if should_escalate else 0,
                reminder_type="work_blocked",
                severity="critical" if should_escalate else "high",
                title=f"经营工作持续阻塞：{item.title}",
                message=(
                    f"Work Item 已阻塞约 {int(blocked_hours)} 小时。原因：{item.blocked_reason or '未填写'}。"
                    + ("已升级给 Pursuit Lead。" if should_escalate else "请尽快解除依赖或调整执行路径。")
                ),
                work_item_id=item.id,
                now=now,
            )
            touched += 1
            escalated += int(should_escalate)

    gates = session.scalars(
        select(PursuitDecisionGateRecord).where(PursuitDecisionGateRecord.status == "open")
    ).all()
    gate_by_id = {gate.id: gate for gate in gates}
    for gate in gates:
        workspace = workspace_by_id.get(gate.workspace_id)
        if workspace is None or not gate.due_at:
            continue
        recipient = workspace.lead_membership_id or gate.opened_by_membership_id
        if recipient is None:
            continue
        due_at = _as_utc(gate.due_at)
        if due_at <= now:
            overdue_hours = (now - due_at).total_seconds() / 3600
            _ensure_reminder(
                session,
                active_keys=active_keys,
                workspace=workspace,
                recipient_membership_id=recipient,
                reminder_type="gate_overdue",
                severity="high",
                title=f"Decision Gate 已到期：{gate.title}",
                message=f"Gate 已超过计划决策时间约 {int(overdue_hours)} 小时，请完成 Review 或记录 HOLD/GO/NO-GO。",
                gate_id=gate.id,
                source_due_at=gate.due_at,
                now=now,
            )
            touched += 1
        elif due_at <= due_soon_until:
            _ensure_reminder(
                session,
                active_keys=active_keys,
                workspace=workspace,
                recipient_membership_id=recipient,
                reminder_type="gate_due_soon",
                severity="warning",
                title=f"Decision Gate 临近：{gate.title}",
                message="Gate 即将到达计划决策时间，请确认 Reviewer、关键依据和决策材料是否齐备。",
                gate_id=gate.id,
                source_due_at=gate.due_at,
                now=now,
            )
            touched += 1

    pending_reviews = session.scalars(
        select(PursuitGateReviewRecord)
        .join(
            PursuitDecisionGateRecord,
            PursuitDecisionGateRecord.id == PursuitGateReviewRecord.gate_id,
        )
        .where(
            PursuitGateReviewRecord.status == "pending",
            PursuitDecisionGateRecord.status == "open",
        )
    ).all()
    for review in pending_reviews:
        gate = gate_by_id.get(review.gate_id)
        if gate is None:
            continue
        workspace = workspace_by_id.get(gate.workspace_id)
        if workspace is None:
            continue
        pending_hours = (now - _as_utc(review.requested_at)).total_seconds() / 3600
        should_escalate = (
            pending_hours >= settings.pursuit_review_escalation_hours
            and workspace.lead_membership_id is not None
            and workspace.lead_membership_id != review.reviewer_membership_id
        )
        _ensure_reminder(
            session,
            active_keys=active_keys,
            workspace=workspace,
            recipient_membership_id=review.reviewer_membership_id,
            escalated_to_membership_id=workspace.lead_membership_id if should_escalate else None,
            escalation_level=1 if should_escalate else 0,
            reminder_type="review_pending",
            severity="high" if should_escalate else "warning",
            title=f"Gate Review 待处理：{gate.title}",
            message=(
                f"Review 已等待约 {int(pending_hours)} 小时。"
                + ("已升级给 Pursuit Lead。" if should_escalate else "请提交复核意见。")
            ),
            gate_id=gate.id,
            review_id=review.id,
            now=now,
        )
        touched += 1
        escalated += int(should_escalate)

    resolved = _resolve_inactive(session, active_keys, now)
    session.commit()
    return {
        "active_conditions": len(active_keys),
        "reminders_touched": touched,
        "escalations_active": escalated,
        "resolved": resolved,
    }


def reminders_for_member(session: Session, principal: Principal) -> dict:
    membership = principal_membership(session, principal)
    rows = session.scalars(
        select(PursuitReminderRecord).where(
            PursuitReminderRecord.status != "resolved",
            or_(
                PursuitReminderRecord.recipient_membership_id == membership.id,
                PursuitReminderRecord.escalated_to_membership_id == membership.id,
            ),
        )
    ).all()
    opportunity_ids = {row.opportunity_id for row in rows}
    titles = {
        row.id: row.title
        for row in session.scalars(
            select(OpportunityRecord).where(OpportunityRecord.id.in_(opportunity_ids))
        ).all()
    } if opportunity_ids else {}
    severity_order = {"critical": 0, "high": 1, "warning": 2, "info": 3}
    rows.sort(
        key=lambda row: (
            severity_order.get(row.severity, 9),
            0 if row.escalated_to_membership_id == membership.id else 1,
            _as_utc(row.source_due_at) if row.source_due_at else _as_utc(row.first_triggered_at),
        )
    )
    return {
        "membership_id": membership.id,
        "count": len(rows),
        "items": [
            {
                "id": row.id,
                "workspace_id": row.workspace_id,
                "opportunity_id": row.opportunity_id,
                "opportunity_title": titles.get(row.opportunity_id, row.opportunity_id),
                "recipient_membership_id": row.recipient_membership_id,
                "escalated_to_membership_id": row.escalated_to_membership_id,
                "is_escalation": row.escalated_to_membership_id == membership.id,
                "work_item_id": row.work_item_id,
                "gate_id": row.gate_id,
                "review_id": row.review_id,
                "type": row.reminder_type,
                "severity": row.severity,
                "status": row.status,
                "title": row.title,
                "message": row.message,
                "source_due_at": row.source_due_at.isoformat() if row.source_due_at else None,
                "escalation_level": row.escalation_level,
                "occurrence_count": row.occurrence_count,
                "first_triggered_at": row.first_triggered_at.isoformat(),
                "last_triggered_at": row.last_triggered_at.isoformat(),
                "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
            }
            for row in rows
        ],
    }


def acknowledge_reminder(
    session: Session,
    *,
    reminder_id: str,
    principal: Principal,
) -> PursuitReminderRecord:
    membership = principal_membership(session, principal)
    row = session.get(PursuitReminderRecord, reminder_id)
    if row is None:
        raise ValueError("pursuit reminder not found")
    allowed = membership.id in {row.recipient_membership_id, row.escalated_to_membership_id}
    if not allowed and ROLE_LEVEL[principal.role] < ROLE_LEVEL["manager"]:
        raise PermissionError("reminder may only be acknowledged by its recipient, escalation owner or manager")
    if row.status != "resolved":
        row.status = "acknowledged"
        row.acknowledged_at = utc_now()
        row.last_evaluated_at = utc_now()
    session.flush()
    return row


def reminder_summary(session: Session) -> dict:
    rows = session.scalars(
        select(PursuitReminderRecord).where(PursuitReminderRecord.status != "resolved")
    ).all()
    return {
        "active": len(rows),
        "critical": sum(1 for row in rows if row.severity == "critical"),
        "escalated": sum(1 for row in rows if row.escalation_level > 0),
        "acknowledged": sum(1 for row in rows if row.status == "acknowledged"),
    }

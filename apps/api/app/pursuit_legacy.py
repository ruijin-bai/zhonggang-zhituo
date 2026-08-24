from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import PursuitActionRecord, WatchItemRecord, utc_now
from .pursuit_db import PursuitWorkItemRecord, PursuitWorkspaceRecord


def sync_legacy_watch(session: Session, watch: WatchItemRecord) -> PursuitWorkspaceRecord:
    """Project a Tracking v1 watch into the canonical Stage B workspace.

    Legacy owner text is intentionally not converted to Membership. A real lead is assigned only
    through the Stage B workspace API where organization membership can be verified.
    """

    workspace = session.scalar(
        select(PursuitWorkspaceRecord).where(
            PursuitWorkspaceRecord.opportunity_id == watch.opportunity_id
        )
    )
    if workspace is None:
        workspace = PursuitWorkspaceRecord(
            id=str(uuid4()),
            opportunity_id=watch.opportunity_id,
            status="active",
            priority=watch.priority,
            lead_membership_id=None,
            created_by_membership_id=None,
            rationale=watch.rationale,
            next_review_at=watch.next_review_at,
        )
        session.add(workspace)
    else:
        workspace.status = "active" if watch.status == "active" else workspace.status
        workspace.priority = watch.priority
        workspace.rationale = watch.rationale
        workspace.next_review_at = watch.next_review_at
        workspace.updated_at = utc_now()
    session.flush()
    return workspace


def _workspace_for_legacy_action(
    session: Session,
    action: PursuitActionRecord,
) -> PursuitWorkspaceRecord:
    workspace = session.scalar(
        select(PursuitWorkspaceRecord).where(
            PursuitWorkspaceRecord.opportunity_id == action.opportunity_id
        )
    )
    if workspace is not None:
        return workspace
    workspace = PursuitWorkspaceRecord(
        id=str(uuid4()),
        opportunity_id=action.opportunity_id,
        status="active",
        priority=action.priority or "medium",
        lead_membership_id=None,
        created_by_membership_id=None,
        rationale="Tracking v1 兼容迁移；待在 Pursuit Workspace 中指定真实负责人。",
        next_review_at=None,
    )
    session.add(workspace)
    session.flush()
    return workspace


def mirror_legacy_action(
    session: Session,
    action: PursuitActionRecord,
) -> PursuitWorkItemRecord:
    """Idempotently mirror a legacy integer Action into the canonical UUID Work Item."""

    existing = session.scalar(
        select(PursuitWorkItemRecord).where(
            PursuitWorkItemRecord.source_action_id == action.id
        )
    )
    workspace = _workspace_for_legacy_action(session, action)
    if existing is None:
        existing = PursuitWorkItemRecord(
            id=str(uuid4()),
            workspace_id=workspace.id,
            opportunity_id=action.opportunity_id,
            work_type="action",
            title=action.title,
            description=action.note or "",
            assignee_membership_id=None,
            created_by_membership_id=None,
            legacy_owner_text=action.owner or None,
            status="done" if action.status == "done" else "open",
            priority=action.priority or "medium",
            due_at=action.due_at,
            blocked_reason=None,
            dependency_work_item_id=None,
            source_action_id=action.id,
            completed_at=action.completed_at,
        )
        session.add(existing)
    else:
        existing.workspace_id = workspace.id
        existing.opportunity_id = action.opportunity_id
        existing.title = action.title
        existing.description = action.note or ""
        existing.legacy_owner_text = action.owner or None
        existing.status = "done" if action.status == "done" else "open"
        existing.priority = action.priority or "medium"
        existing.due_at = action.due_at
        existing.completed_at = action.completed_at
        existing.updated_at = utc_now()
    session.flush()
    return existing


def sync_legacy_tracking_snapshot(session: Session, opportunity_id: str) -> None:
    watch = session.scalar(
        select(WatchItemRecord).where(WatchItemRecord.opportunity_id == opportunity_id)
    )
    if watch is not None:
        sync_legacy_watch(session, watch)
    actions = session.scalars(
        select(PursuitActionRecord).where(PursuitActionRecord.opportunity_id == opportunity_id)
    ).all()
    for action in actions:
        mirror_legacy_action(session, action)

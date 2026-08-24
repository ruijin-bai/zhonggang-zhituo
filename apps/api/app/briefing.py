from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import (
    OpportunityDraftRecord,
    OpportunityEventRecord,
    OpportunityRecord,
    PursuitActionRecord,
    PursuitAlertRecord,
    WatchItemRecord,
    utc_now,
)


def _opportunity_titles(session: Session, opportunity_ids: set[str]) -> dict[str, str]:
    if not opportunity_ids:
        return {}
    rows = session.execute(
        select(OpportunityRecord.id, OpportunityRecord.title).where(
            OpportunityRecord.id.in_(opportunity_ids)
        )
    ).all()
    return {row.id: row.title for row in rows}


def daily_brief(session: Session, *, window_hours: int = 24, limit: int = 8) -> dict:
    """Build a tenant-scoped operational briefing from existing system-of-record facts.

    This is deliberately a read model, not another persisted state table. Every query remains
    subject to the current SQLAlchemy tenant criteria and PostgreSQL RLS context.
    """

    now = utc_now()
    since = now - timedelta(hours=window_hours)
    due_soon_until = now + timedelta(days=7)

    pending_candidates = session.scalar(
        select(func.count())
        .select_from(OpportunityDraftRecord)
        .where(OpportunityDraftRecord.status == "pending")
    ) or 0
    new_candidates = session.scalar(
        select(func.count())
        .select_from(OpportunityDraftRecord)
        .where(
            OpportunityDraftRecord.status == "pending",
            OpportunityDraftRecord.created_at >= since,
        )
    ) or 0
    recent_event_count = session.scalar(
        select(func.count())
        .select_from(OpportunityEventRecord)
        .where(OpportunityEventRecord.occurred_at >= since)
    ) or 0
    open_alert_count = session.scalar(
        select(func.count())
        .select_from(PursuitAlertRecord)
        .where(PursuitAlertRecord.status == "open")
    ) or 0
    overdue_action_count = session.scalar(
        select(func.count())
        .select_from(PursuitActionRecord)
        .where(
            PursuitActionRecord.status != "completed",
            PursuitActionRecord.due_at.is_not(None),
            PursuitActionRecord.due_at < now,
        )
    ) or 0
    due_soon_action_count = session.scalar(
        select(func.count())
        .select_from(PursuitActionRecord)
        .where(
            PursuitActionRecord.status != "completed",
            PursuitActionRecord.due_at.is_not(None),
            PursuitActionRecord.due_at >= now,
            PursuitActionRecord.due_at <= due_soon_until,
        )
    ) or 0
    review_due_count = session.scalar(
        select(func.count())
        .select_from(WatchItemRecord)
        .where(
            WatchItemRecord.status == "active",
            WatchItemRecord.next_review_at.is_not(None),
            WatchItemRecord.next_review_at <= now,
        )
    ) or 0

    event_rows = session.scalars(
        select(OpportunityEventRecord)
        .where(OpportunityEventRecord.occurred_at >= since)
        .order_by(OpportunityEventRecord.occurred_at.desc())
        .limit(limit)
    ).all()

    overdue_rows = session.scalars(
        select(PursuitActionRecord)
        .where(
            PursuitActionRecord.status != "completed",
            PursuitActionRecord.due_at.is_not(None),
            PursuitActionRecord.due_at < now,
        )
        .order_by(PursuitActionRecord.due_at.asc())
        .limit(limit)
    ).all()
    alert_rows = session.scalars(
        select(PursuitAlertRecord)
        .where(PursuitAlertRecord.status == "open")
        .order_by(PursuitAlertRecord.created_at.desc())
        .limit(limit)
    ).all()
    review_rows = session.scalars(
        select(WatchItemRecord)
        .where(
            WatchItemRecord.status == "active",
            WatchItemRecord.next_review_at.is_not(None),
            WatchItemRecord.next_review_at <= now,
        )
        .order_by(WatchItemRecord.next_review_at.asc())
        .limit(limit)
    ).all()
    candidate_rows = session.scalars(
        select(OpportunityDraftRecord)
        .where(OpportunityDraftRecord.status == "pending")
        .order_by(OpportunityDraftRecord.created_at.desc())
        .limit(limit)
    ).all()

    opportunity_ids = {
        *(item.opportunity_id for item in event_rows),
        *(item.opportunity_id for item in overdue_rows),
        *(item.opportunity_id for item in alert_rows),
        *(item.opportunity_id for item in review_rows),
    }
    titles = _opportunity_titles(session, opportunity_ids)

    recent_events = [
        {
            "kind": "opportunity_event",
            "event_type": row.event_type,
            "opportunity_id": row.opportunity_id,
            "title": titles.get(row.opportunity_id, row.opportunity_id),
            "occurred_at": row.occurred_at.isoformat(),
            "payload": row.payload or {},
        }
        for row in event_rows
    ]

    attention: list[dict] = []
    attention.extend(
        {
            "kind": "overdue_action",
            "severity": "high",
            "resource_id": str(row.id),
            "opportunity_id": row.opportunity_id,
            "title": row.title,
            "subtitle": titles.get(row.opportunity_id, row.opportunity_id),
            "owner": row.owner,
            "due_at": row.due_at.isoformat() if row.due_at else None,
        }
        for row in overdue_rows
    )
    attention.extend(
        {
            "kind": "open_alert",
            "severity": row.severity,
            "resource_id": str(row.id),
            "opportunity_id": row.opportunity_id,
            "title": row.title,
            "subtitle": titles.get(row.opportunity_id, row.opportunity_id),
            "message": row.message,
            "created_at": row.created_at.isoformat(),
        }
        for row in alert_rows
    )
    attention.extend(
        {
            "kind": "review_due",
            "severity": "medium",
            "resource_id": str(row.id),
            "opportunity_id": row.opportunity_id,
            "title": f"重点机会到期复盘：{titles.get(row.opportunity_id, row.opportunity_id)}",
            "subtitle": row.owner,
            "due_at": row.next_review_at.isoformat() if row.next_review_at else None,
        }
        for row in review_rows
    )
    attention.extend(
        {
            "kind": "candidate_review",
            "severity": "medium",
            "resource_id": row.id,
            "opportunity_id": None,
            "title": (row.discovery or {}).get("title") or row.source_title,
            "subtitle": f"{row.publisher} · {row.source_rank}级来源",
            "created_at": row.created_at.isoformat(),
        }
        for row in candidate_rows
    )

    severity_order = {"critical": 0, "high": 1, "warning": 2, "medium": 3, "info": 4}
    attention.sort(key=lambda item: severity_order.get(str(item.get("severity", "medium")), 3))
    attention = attention[: max(limit * 2, limit)]

    return {
        "generated_at": now.isoformat(),
        "window_hours": window_hours,
        "summary": {
            "pending_candidates": pending_candidates,
            "new_candidates": new_candidates,
            "recent_events": recent_event_count,
            "open_alerts": open_alert_count,
            "overdue_actions": overdue_action_count,
            "due_soon_actions": due_soon_action_count,
            "review_due": review_due_count,
        },
        "recent_events": recent_events,
        "attention": attention,
        "note": (
            "Daily Brief 直接聚合当前租户的 Candidate、Opportunity Event、Action、Alert 与 Watch 事实；"
            "它是实时读模型，不创建第二套业务状态。"
        ),
    }

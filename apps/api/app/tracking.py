from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import OpportunityEventRecord, PursuitActionRecord, PursuitAlertRecord, WatchItemRecord
from .repository import get_opportunity, list_opportunities


class WatchUpsert(BaseModel):
    priority: str = "medium"
    owner: str = "未指定"
    rationale: str = ""
    next_review_at: datetime | None = None


class ActionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    owner: str = "未指定"
    priority: str = "medium"
    due_at: datetime | None = None
    note: str = ""


class TrackingBoard(BaseModel):
    watch_count: int
    open_action_count: int
    overdue_action_count: int
    open_alert_count: int
    items: list[dict]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_alerts(session: Session) -> None:
    now = _now()
    watched = session.scalars(select(WatchItemRecord).where(WatchItemRecord.status == "active")).all()
    for watch in watched:
        opportunity = get_opportunity(watch.opportunity_id, session)
        if not opportunity:
            continue
        existing_types = set(
            session.scalars(
                select(PursuitAlertRecord.alert_type).where(
                    PursuitAlertRecord.opportunity_id == watch.opportunity_id,
                    PursuitAlertRecord.status == "open",
                )
            ).all()
        )
        if opportunity.confidence < 55 and "low_confidence" not in existing_types:
            session.add(PursuitAlertRecord(opportunity_id=watch.opportunity_id, severity="warning", alert_type="low_confidence", title="关键证据不足", message=f"当前研判置信度仅 {opportunity.confidence}%，建议优先补齐融资、业主和采购证据。"))
        if opportunity.grade == "A" and opportunity.decision == "GO" and "high_priority" not in existing_types:
            session.add(PursuitAlertRecord(opportunity_id=watch.opportunity_id, severity="high", alert_type="high_priority", title="高潜机会进入重点经营窗口", message="项目已达到 A 级且建议 GO，请检查经营行动、关键人和采购窗口是否已覆盖。"))
        if watch.next_review_at and watch.next_review_at < now and "review_due" not in existing_types:
            session.add(PursuitAlertRecord(opportunity_id=watch.opportunity_id, severity="warning", alert_type="review_due", title="项目复盘已到期", message="重点跟踪项目已超过计划复盘时间，请更新状态、证据和下一步行动。"))

    overdue = session.scalars(select(PursuitActionRecord).where(PursuitActionRecord.status == "open", PursuitActionRecord.due_at.is_not(None), PursuitActionRecord.due_at < now)).all()
    for action in overdue:
        exists = session.scalar(select(PursuitAlertRecord).where(PursuitAlertRecord.opportunity_id == action.opportunity_id, PursuitAlertRecord.status == "open", PursuitAlertRecord.alert_type == f"action_overdue:{action.id}"))
        if not exists:
            session.add(PursuitAlertRecord(opportunity_id=action.opportunity_id, severity="high", alert_type=f"action_overdue:{action.id}", title="经营行动已逾期", message=f"行动“{action.title}”已超过计划完成时间。"))
    session.commit()


def get_tracking_board(session: Session) -> TrackingBoard:
    try:
        _ensure_alerts(session)
        watches = session.scalars(select(WatchItemRecord).where(WatchItemRecord.status == "active").order_by(WatchItemRecord.priority.asc(), WatchItemRecord.updated_at.desc())).all()
        actions = session.scalars(select(PursuitActionRecord).order_by(PursuitActionRecord.created_at.desc())).all()
        alerts = session.scalars(select(PursuitAlertRecord).where(PursuitAlertRecord.status == "open").order_by(PursuitAlertRecord.created_at.desc())).all()
        events = session.scalars(select(OpportunityEventRecord).order_by(OpportunityEventRecord.occurred_at.desc()).limit(100)).all()
    except SQLAlchemyError:
        session.rollback()
        # read-only demo fallback: surface A/B opportunities as suggested tracking items
        items = []
        for item in list_opportunities(session)[:5]:
            items.append({"opportunity": item.model_dump(), "watch": None, "actions": [], "alerts": [], "timeline": []})
        return TrackingBoard(watch_count=0, open_action_count=0, overdue_action_count=0, open_alert_count=0, items=items)

    by_actions: dict[str, list] = {}
    by_alerts: dict[str, list] = {}
    by_events: dict[str, list] = {}
    now = _now()
    for action in actions: by_actions.setdefault(action.opportunity_id, []).append(action)
    for alert in alerts: by_alerts.setdefault(alert.opportunity_id, []).append(alert)
    for event in events: by_events.setdefault(event.opportunity_id, []).append(event)

    items = []
    for watch in watches:
        opportunity = get_opportunity(watch.opportunity_id, session)
        if not opportunity: continue
        items.append({
            "opportunity": opportunity.model_dump(),
            "watch": {"id": watch.id, "priority": watch.priority, "owner": watch.owner, "rationale": watch.rationale, "next_review_at": watch.next_review_at.isoformat() if watch.next_review_at else None},
            "actions": [{"id": a.id, "title": a.title, "owner": a.owner, "priority": a.priority, "status": a.status, "due_at": a.due_at.isoformat() if a.due_at else None, "note": a.note} for a in by_actions.get(watch.opportunity_id, [])],
            "alerts": [{"id": a.id, "severity": a.severity, "type": a.alert_type, "title": a.title, "message": a.message, "created_at": a.created_at.isoformat()} for a in by_alerts.get(watch.opportunity_id, [])],
            "timeline": [{"type": e.event_type, "at": e.occurred_at.isoformat(), "payload": e.payload} for e in by_events.get(watch.opportunity_id, [])[:8]],
        })
    open_actions = [a for a in actions if a.status == "open"]
    return TrackingBoard(watch_count=len(watches), open_action_count=len(open_actions), overdue_action_count=sum(1 for a in open_actions if a.due_at and a.due_at < now), open_alert_count=len(alerts), items=items)


def watch_opportunity(opportunity_id: str, payload: WatchUpsert, session: Session) -> dict:
    if not get_opportunity(opportunity_id, session): raise ValueError("机会不存在")
    record = session.scalar(select(WatchItemRecord).where(WatchItemRecord.opportunity_id == opportunity_id))
    if record is None:
        record = WatchItemRecord(opportunity_id=opportunity_id)
        session.add(record)
    record.priority = payload.priority
    record.owner = payload.owner
    record.rationale = payload.rationale
    record.next_review_at = payload.next_review_at
    record.status = "active"
    session.add(OpportunityEventRecord(opportunity_id=opportunity_id, event_type="watch_updated", payload=payload.model_dump(mode="json")))
    session.commit()
    return {"ok": True, "opportunity_id": opportunity_id}


def add_action(opportunity_id: str, payload: ActionCreate, session: Session) -> dict:
    if not get_opportunity(opportunity_id, session): raise ValueError("机会不存在")
    record = PursuitActionRecord(opportunity_id=opportunity_id, **payload.model_dump())
    session.add(record)
    session.flush()
    session.add(OpportunityEventRecord(opportunity_id=opportunity_id, event_type="action_created", payload={"action_id": record.id, "title": record.title}))
    session.commit()
    return {"ok": True, "action_id": record.id}


def complete_action(action_id: int, session: Session) -> dict:
    action = session.get(PursuitActionRecord, action_id)
    if not action: raise ValueError("行动不存在")
    action.status = "done"
    action.completed_at = _now()
    session.add(OpportunityEventRecord(opportunity_id=action.opportunity_id, event_type="action_completed", payload={"action_id": action.id, "title": action.title}))
    session.commit()
    return {"ok": True, "action_id": action.id}


def resolve_alert(alert_id: int, session: Session) -> dict:
    alert = session.get(PursuitAlertRecord, alert_id)
    if not alert: raise ValueError("预警不存在")
    alert.status = "resolved"
    alert.resolved_at = _now()
    session.commit()
    return {"ok": True, "alert_id": alert.id}

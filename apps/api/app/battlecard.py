from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import OpportunityEventRecord, PursuitActionRecord, PursuitAlertRecord, WatchItemRecord
from .repository import get_opportunity
from .strategy import get_strategy


def _events(opportunity_id:str,session:Session):
 try:return session.scalars(select(OpportunityEventRecord).where(OpportunityEventRecord.opportunity_id==opportunity_id,OpportunityEventRecord.event_type=="strategy_updated").order_by(OpportunityEventRecord.occurred_at.desc()).limit(10)).all()
 except SQLAlchemyError:session.rollback();return []

def get_battlecard(opportunity_id:str,session:Session)->dict:
 o=get_opportunity(opportunity_id,session)
 if not o:raise ValueError("机会不存在")
 ws=get_strategy(opportunity_id,session)
 try:
  watch=session.scalar(select(WatchItemRecord).where(WatchItemRecord.opportunity_id==opportunity_id))
  actions=session.scalars(select(PursuitActionRecord).where(PursuitActionRecord.opportunity_id==opportunity_id,PursuitActionRecord.status=="open").order_by(PursuitActionRecord.priority,PursuitActionRecord.due_at).limit(6)).all()
  alerts=session.scalars(select(PursuitAlertRecord).where(PursuitAlertRecord.opportunity_id==opportunity_id,PursuitAlertRecord.status=="open").order_by(PursuitAlertRecord.created_at.desc()).limit(5)).all()
 except SQLAlchemyError:session.rollback();watch=None;actions=[];alerts=[]
 versions=_events(opportunity_id,session)
 strategy=ws.strategy
 return {"generated_at":datetime.now(timezone.utc).isoformat(),"opportunity":o.model_dump(mode="json"),"strategy":{"readiness":ws.readiness,"label":ws.readiness_label,"win_theme":strategy.get("win_theme"),"client_need":strategy.get("client_need"),"differentiation":strategy.get("differentiation",[])[:4],"gaps":strategy.get("gaps",[])[:4],"competitors":strategy.get("competitors",[])[:4],"stakeholders":strategy.get("stakeholders",[])[:5]},"execution":{"owner":watch.owner if watch else "未指定","priority":watch.priority if watch else "未纳入重点跟踪","next_review_at":watch.next_review_at.isoformat() if watch and watch.next_review_at else None,"actions":[{"title":x.title,"owner":x.owner,"priority":x.priority,"due_at":x.due_at.isoformat() if x.due_at else None} for x in actions],"alerts":[{"severity":x.severity,"title":x.title,"message":x.message} for x in alerts]},"versions":[{"version":len(versions)-i,"at":x.occurred_at.isoformat(),"win_theme":x.payload.get("win_theme",""),"gaps":x.payload.get("gaps",[])} for i,x in enumerate(versions)],"decision_line":f"{o.decision}｜机会{o.score}分/{o.grade}级｜策略成熟度{ws.readiness}%"}

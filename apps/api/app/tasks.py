import asyncio

from celery.exceptions import SoftTimeLimitExceeded

from .ai import AIService
from .celery_app import celery_app
from .db import SessionLocal, set_tenant_context
from .discovery import discover
from .ingestion import ingest_source
from .models import DiscoverRequest, SourceIngestRequest
from .radar import BatchScanRequest, batch_scan
from .repository import get_opportunity
from .strategy import get_strategy
from .strategy_ai import generate_strategy, red_team


def _json(model):
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else model


def _tenant_session(organization_id: str):
    session = SessionLocal()
    set_tenant_context(session, organization_id)
    return session


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.discovery.scan")
def discovery_scan_task(self, payload: dict, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            result = asyncio.run(discover(DiscoverRequest.model_validate(payload), session))
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("商机发现任务超过软超时限制") from exc


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.discovery.batch")
def discovery_batch_task(self, payload: dict, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            result = asyncio.run(batch_scan(BatchScanRequest.model_validate(payload), session))
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("批量商机扫描任务超过软超时限制") from exc


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.source.ingest")
def source_ingest_task(self, payload: dict, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            result = asyncio.run(ingest_source(SourceIngestRequest.model_validate(payload), session))
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("情报抽取任务超过软超时限制") from exc


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 2}, name="zhituo.opportunity.analyze")
def opportunity_analyze_task(self, opportunity_id: str, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            item = get_opportunity(opportunity_id, session)
            if item is None:
                raise ValueError("Opportunity not found")
            analysis, mode = asyncio.run(AIService().analyze(item))
            return {"mode": mode, "opportunity_id": opportunity_id, "analysis": _json(analysis)}
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("AI 经营研判任务超过软超时限制") from exc


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 2}, name="zhituo.strategy.generate")
def strategy_generate_task(self, opportunity_id: str, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            item = get_opportunity(opportunity_id, session)
            if item is None:
                raise ValueError("Opportunity not found")
            draft, mode = asyncio.run(generate_strategy(item))
            return {"mode": mode, "opportunity_id": opportunity_id, "draft": _json(draft)}
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("赢标策略生成任务超过软超时限制") from exc


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 2}, name="zhituo.strategy.red_team")
def strategy_red_team_task(self, opportunity_id: str, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            item = get_opportunity(opportunity_id, session)
            if item is None:
                raise ValueError("Opportunity not found")
            workspace = get_strategy(opportunity_id, session)
            challenge, mode = asyncio.run(red_team(item, workspace.strategy))
            return {"mode": mode, "opportunity_id": opportunity_id, "challenge": _json(challenge)}
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("红队挑战任务超过软超时限制") from exc

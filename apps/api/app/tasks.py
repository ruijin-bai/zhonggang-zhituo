import asyncio

from celery.exceptions import SoftTimeLimitExceeded

from .ai import AIService
from .celery_app import celery_app
from .db import SessionLocal
from .discovery import discover
from .ingestion import ingest_source
from .models import DiscoverRequest, SourceIngestRequest
from .radar import BatchScanRequest, batch_scan
from .repository import get_opportunity


def _json(model):
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else model


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.discovery.scan")
def discovery_scan_task(self, payload: dict) -> dict:
    try:
        with SessionLocal() as session:
            result = asyncio.run(discover(DiscoverRequest.model_validate(payload), session))
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("商机发现任务超过软超时限制") from exc


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.discovery.batch")
def discovery_batch_task(self, payload: dict) -> dict:
    try:
        with SessionLocal() as session:
            result = asyncio.run(batch_scan(BatchScanRequest.model_validate(payload), session))
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("批量商机扫描任务超过软超时限制") from exc


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.source.ingest")
def source_ingest_task(self, payload: dict) -> dict:
    try:
        with SessionLocal() as session:
            result = asyncio.run(ingest_source(SourceIngestRequest.model_validate(payload), session))
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("情报抽取任务超过软超时限制") from exc


@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 2}, name="zhituo.opportunity.analyze")
def opportunity_analyze_task(self, opportunity_id: str) -> dict:
    try:
        with SessionLocal() as session:
            item = get_opportunity(opportunity_id, session)
            if item is None:
                raise ValueError("Opportunity not found")
            analysis, mode = asyncio.run(AIService().analyze(item))
            return {"mode": mode, "opportunity_id": opportunity_id, "analysis": _json(analysis)}
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("AI 经营研判任务超过软超时限制") from exc

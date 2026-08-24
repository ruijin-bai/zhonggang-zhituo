import asyncio

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select

from .ai import AIService
from .candidate_pipeline import (
    claim_candidate_processing,
    process_candidate_document,
    release_candidate_dispatch_claim,
)
from .celery_app import celery_app
from .db import OrganizationRecord, SessionLocal, set_tenant_context
from .discovery import discover
from .ingestion import ingest_source
from .job_ledger import count_stale_queued_jobs, reconcile_stuck_jobs
from .metrics import set_stale_queued_jobs
from .models import DiscoverRequest, SourceIngestRequest
from .radar import BatchScanRequest, batch_scan
from .repository import get_opportunity
from .source_archive import SourceFetchRequest, fetch_and_archive_source
from .source_monitoring import (
    claim_due_subscriptions,
    release_dispatch_claim,
    scan_subscription,
)
from .strategy import get_strategy
from .strategy_ai import generate_strategy, red_team
from .tracked_task import TrackedTask


def _json(model):
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else model


def _tenant_session(organization_id: str):
    session = SessionLocal()
    set_tenant_context(session, organization_id)
    return session


def _active_organization_ids() -> list[str]:
    with SessionLocal() as control_session:
        return list(
            control_session.scalars(
                select(OrganizationRecord.id).where(OrganizationRecord.is_active.is_(True))
            ).all()
        )


@celery_app.task(name="zhituo.maintenance.reconcile_stuck_jobs")
def reconcile_stuck_jobs_task() -> dict:
    organization_ids = _active_organization_ids()
    reconciled: list[str] = []
    stale_queued = 0
    for organization_id in organization_ids:
        with _tenant_session(organization_id) as session:
            stale_queued += count_stale_queued_jobs(session)
            reconciled.extend(reconcile_stuck_jobs(session))
    set_stale_queued_jobs(stale_queued)
    return {
        "organizations_scanned": len(organization_ids),
        "reconciled": reconciled,
        "stale_queued": stale_queued,
    }


@celery_app.task(name="zhituo.sources.dispatch_due_scans")
def dispatch_due_source_scans_task() -> dict:
    organization_ids = _active_organization_ids()
    claimed = 0
    dispatched = 0
    dispatch_failures: list[dict] = []
    for organization_id in organization_ids:
        with _tenant_session(organization_id) as session:
            claims = claim_due_subscriptions(session)
        claimed += len(claims)
        for subscription_id, lease_token in claims:
            try:
                source_subscription_scan_task.apply_async(
                    args=(subscription_id, organization_id, False, lease_token),
                    headers={"organization_id": organization_id},
                )
                dispatched += 1
            except Exception as exc:
                with _tenant_session(organization_id) as session:
                    release_dispatch_claim(
                        session,
                        subscription_id,
                        str(exc),
                        lease_token=lease_token,
                    )
                dispatch_failures.append(
                    {"subscription_id": subscription_id, "error": str(exc)[:500]}
                )
    return {
        "organizations_scanned": len(organization_ids),
        "claimed": claimed,
        "dispatched": dispatched,
        "dispatch_failures": dispatch_failures,
    }


@celery_app.task(name="zhituo.sources.scan_subscription")
def source_subscription_scan_task(
    subscription_id: str,
    organization_id: str,
    manual: bool = False,
    lease_token: str | None = None,
) -> dict:
    with _tenant_session(organization_id) as session:
        result = asyncio.run(
            scan_subscription(
                session,
                subscription_id,
                manual=manual,
                lease_token=lease_token,
            )
        )
        return _json(result)


@celery_app.task(name="zhituo.candidates.dispatch_pending")
def dispatch_pending_candidates_task() -> dict:
    organization_ids = _active_organization_ids()
    claimed = 0
    dispatched = 0
    dispatch_failures: list[dict] = []
    for organization_id in organization_ids:
        with _tenant_session(organization_id) as session:
            claims = claim_candidate_processing(session)
        claimed += len(claims)
        for processing_id, lease_token in claims:
            try:
                process_candidate_document_task.apply_async(
                    args=(processing_id, organization_id, lease_token),
                    headers={"organization_id": organization_id},
                )
                dispatched += 1
            except Exception as exc:
                with _tenant_session(organization_id) as session:
                    release_candidate_dispatch_claim(
                        session,
                        processing_id,
                        str(exc),
                        lease_token=lease_token,
                    )
                dispatch_failures.append(
                    {"processing_id": processing_id, "error": str(exc)[:500]}
                )
    return {
        "organizations_scanned": len(organization_ids),
        "claimed": claimed,
        "dispatched": dispatched,
        "dispatch_failures": dispatch_failures,
    }


@celery_app.task(name="zhituo.candidates.process_document")
def process_candidate_document_task(
    processing_id: str,
    organization_id: str,
    lease_token: str,
) -> dict:
    with _tenant_session(organization_id) as session:
        result = asyncio.run(
            process_candidate_document(
                session,
                processing_id,
                lease_token=lease_token,
            )
        )
        return _json(result)


@celery_app.task(bind=True, base=TrackedTask, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.discovery.scan")
def discovery_scan_task(self, payload: dict, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            result = asyncio.run(discover(DiscoverRequest.model_validate(payload), session))
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("商机发现任务超过软超时限制") from exc


@celery_app.task(bind=True, base=TrackedTask, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.discovery.batch")
def discovery_batch_task(self, payload: dict, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            result = asyncio.run(batch_scan(BatchScanRequest.model_validate(payload), session))
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("批量商机扫描任务超过软超时限制") from exc


@celery_app.task(bind=True, base=TrackedTask, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.source.fetch_archive")
def source_fetch_archive_task(self, payload: dict, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            result = asyncio.run(
                fetch_and_archive_source(SourceFetchRequest.model_validate(payload), session)
            )
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("外部来源抓取归档任务超过软超时限制") from exc


@celery_app.task(bind=True, base=TrackedTask, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3}, name="zhituo.source.ingest")
def source_ingest_task(self, payload: dict, organization_id: str) -> dict:
    try:
        with _tenant_session(organization_id) as session:
            result = asyncio.run(ingest_source(SourceIngestRequest.model_validate(payload), session))
            return _json(result)
    except SoftTimeLimitExceeded as exc:
        raise RuntimeError("情报抽取任务超过软超时限制") from exc


@celery_app.task(bind=True, base=TrackedTask, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 2}, name="zhituo.opportunity.analyze")
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


@celery_app.task(bind=True, base=TrackedTask, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 2}, name="zhituo.strategy.generate")
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


@celery_app.task(bind=True, base=TrackedTask, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 2}, name="zhituo.strategy.red_team")
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
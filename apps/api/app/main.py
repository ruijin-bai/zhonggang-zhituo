from importlib.metadata import PackageNotFoundError, version

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .admin import router as admin_router
from .ai import AIService
from .audit import write_audit
from .battlecard import get_battlecard
from .business_idempotency import begin_operation, complete_operation, fail_operation
from .config import get_settings
from .db import get_db
from .discovery import confirm_draft, discover
from .ingestion import ingest_source
from .jobs import router as jobs_router
from .models import (
    AnalysisResult,
    ConfirmDraftRequest,
    ConfirmDraftResult,
    DiscoverRequest,
    DiscoverResult,
    IngestResult,
    Opportunity,
    SourceIngestRequest,
)
from .observability import configure_logging, install_observability
from .radar import BatchScanRequest, BatchScanResult, RadarOverview, batch_scan, get_radar
from .repository import get_opportunity, list_opportunities
from .scoring import calculate_score
from .security import Principal, get_principal, require_role
from .strategy import StrategyUpsert, StrategyWorkspace, get_strategy, save_strategy
from .strategy_ai import generate_strategy, red_team
from .tracking import (
    ActionCreate,
    TrackingBoard,
    WatchUpsert,
    add_action,
    complete_action,
    get_tracking_board,
    resolve_alert,
    watch_opportunity,
)

settings = get_settings()
configure_logging()
try:
    APP_VERSION = version("zhituo-api")
except PackageNotFoundError:
    APP_VERSION = "0.12.0"

app = FastAPI(title="中港智拓 API", version=APP_VERSION)
install_observability(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-Request-ID",
        "X-Correlation-ID",
        "X-Zhituo-User",
        "X-Zhituo-Gateway-Secret",
        "X-Zhituo-Organization",
    ],
)
app.include_router(admin_router)
app.include_router(jobs_router)


def _inline_only(job_endpoint: str) -> None:
    if settings.job_mode == "queue":
        raise HTTPException(status_code=409, detail=f"Queued execution required. Use {job_endpoint}")


def _idempotency_key(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "zhituo-api",
        "version": APP_VERSION,
        "job_mode": settings.job_mode,
    }


@app.get("/api/meta")
def meta(principal: Principal = Depends(get_principal)) -> dict:
    return {
        "version": APP_VERSION,
        "data_backend": settings.data_backend,
        "job_mode": settings.job_mode,
        "ai_enabled": settings.ai_enabled,
        "auth_mode": settings.auth_mode,
        "rls_enabled": settings.database_rls_enabled,
        "organization": principal.organization_name,
        "role": principal.role,
    }


@app.get("/api/opportunities", response_model=list[Opportunity])
def opportunities(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[Opportunity]:
    return list_opportunities(db)


@app.get("/api/opportunities/{opportunity_id}", response_model=Opportunity)
def opportunity_detail(
    opportunity_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Opportunity:
    item = get_opportunity(opportunity_id, db)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return item


@app.get("/api/opportunities/{opportunity_id}/score")
def opportunity_score(
    opportunity_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    item = get_opportunity(opportunity_id, db)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    result = calculate_score(item.breakdown, item.confidence)
    return {
        "opportunity_id": item.id,
        "total": result.total,
        "grade": result.grade,
        "decision": result.decision,
        "confidence": item.confidence,
        "breakdown": item.breakdown,
    }


@app.get("/api/opportunities/{opportunity_id}/battlecard")
def opportunity_battlecard(
    opportunity_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    try:
        return get_battlecard(opportunity_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/radar", response_model=RadarOverview)
def market_radar(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> RadarOverview:
    return get_radar(db)


@app.post("/api/discovery/batch", response_model=BatchScanResult, deprecated=True)
async def discovery_batch(
    request: BatchScanRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> BatchScanResult:
    _inline_only("/api/jobs/discovery/batch")
    result = await batch_scan(request, db)
    write_audit(
        db,
        principal=principal,
        action="discovery.batch.inline",
        resource_type="source",
        request=http_request,
        details={"scanned": result.scanned, "discovered": result.discovered},
    )
    db.commit()
    return result


@app.post("/api/sources/ingest", response_model=IngestResult, deprecated=True)
async def source_ingest(
    request: SourceIngestRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> IngestResult:
    _inline_only("/api/jobs/sources/ingest")
    result = await ingest_source(request, db)
    write_audit(
        db,
        principal=principal,
        action="source.ingest.inline",
        resource_type="opportunity",
        resource_id=request.opportunity_id,
        request=http_request,
        details={
            "persisted": result.persisted,
            "mode": result.extraction_mode,
            "applied_fields": result.applied_fields,
        },
    )
    db.commit()
    return result


@app.post("/api/discovery/scan", response_model=DiscoverResult, deprecated=True)
async def discovery_scan(
    request: DiscoverRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
) -> DiscoverResult:
    _inline_only("/api/jobs/discovery/scan")
    try:
        result = await discover(request, db)
        write_audit(
            db,
            principal=principal,
            action="discovery.scan.inline",
            resource_type="draft",
            resource_id=result.draft.id,
            request=http_request,
            details={"persisted": result.draft.persisted},
        )
        db.commit()
        return result
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/discovery/drafts/{draft_id}/confirm", response_model=ConfirmDraftResult)
def discovery_confirm(
    draft_id: str,
    request: ConfirmDraftRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> ConfirmDraftResult:
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"draft.confirm:{draft_id}",
        raw_key=_idempotency_key(http_request),
        request_payload=request.model_dump(mode="json"),
    )
    if handle.is_replay:
        return ConfirmDraftResult.model_validate(handle.replay_payload)
    try:
        result = confirm_draft(draft_id, request, db)
        write_audit(
            db,
            principal=principal,
            action="draft.confirm",
            resource_type="opportunity",
            resource_id=result.opportunity.id,
            request=http_request,
            details={"draft_id": draft_id},
        )
        db.commit()
        complete_operation(db, handle, result.model_dump(mode="json"))
        return result
    except ValueError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@app.get("/api/tracking", response_model=TrackingBoard)
def tracking_board(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> TrackingBoard:
    return get_tracking_board(db)


@app.put("/api/tracking/{opportunity_id}/watch")
def tracking_watch(
    opportunity_id: str,
    request: WatchUpsert,
    http_request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"tracking.watch:{opportunity_id}",
        raw_key=_idempotency_key(http_request),
        request_payload=request.model_dump(mode="json"),
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        result = watch_opportunity(opportunity_id, request, db)
        write_audit(
            db,
            principal=principal,
            action="tracking.watch",
            resource_type="opportunity",
            resource_id=opportunity_id,
            request=http_request,
        )
        db.commit()
        complete_operation(db, handle, result)
        return result
    except ValueError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@app.post("/api/tracking/{opportunity_id}/actions")
def tracking_add_action(
    opportunity_id: str,
    request: ActionCreate,
    http_request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"action.create:{opportunity_id}",
        raw_key=_idempotency_key(http_request),
        request_payload=request.model_dump(mode="json"),
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        result = add_action(opportunity_id, request, db)
        write_audit(
            db,
            principal=principal,
            action="action.create",
            resource_type="opportunity",
            resource_id=opportunity_id,
            request=http_request,
            details={"title": request.title},
        )
        db.commit()
        complete_operation(db, handle, result)
        return result
    except ValueError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@app.post("/api/tracking/actions/{action_id}/complete")
def tracking_complete_action(
    action_id: int,
    http_request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"action.complete:{action_id}",
        raw_key=_idempotency_key(http_request),
        request_payload={"action_id": action_id},
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        result = complete_action(action_id, db)
        write_audit(
            db,
            principal=principal,
            action="action.complete",
            resource_type="action",
            resource_id=str(action_id),
            request=http_request,
        )
        db.commit()
        complete_operation(db, handle, result)
        return result
    except ValueError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@app.post("/api/tracking/alerts/{alert_id}/resolve")
def tracking_resolve_alert(
    alert_id: int,
    http_request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"alert.resolve:{alert_id}",
        raw_key=_idempotency_key(http_request),
        request_payload={"alert_id": alert_id},
    )
    if handle.is_replay:
        return handle.replay_payload
    try:
        result = resolve_alert(alert_id, db)
        write_audit(
            db,
            principal=principal,
            action="alert.resolve",
            resource_type="alert",
            resource_id=str(alert_id),
            request=http_request,
        )
        db.commit()
        complete_operation(db, handle, result)
        return result
    except ValueError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@app.get("/api/opportunities/{opportunity_id}/strategy", response_model=StrategyWorkspace)
def pursuit_strategy(
    opportunity_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> StrategyWorkspace:
    try:
        return get_strategy(opportunity_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/opportunities/{opportunity_id}/strategy", response_model=StrategyWorkspace)
def pursuit_strategy_update(
    opportunity_id: str,
    request: StrategyUpsert,
    http_request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("manager")),
) -> StrategyWorkspace:
    handle = begin_operation(
        db,
        organization_id=principal.organization_id,
        scope=f"strategy.update:{opportunity_id}",
        raw_key=_idempotency_key(http_request),
        request_payload=request.model_dump(mode="json"),
    )
    if handle.is_replay:
        return StrategyWorkspace.model_validate(handle.replay_payload)
    try:
        result = save_strategy(opportunity_id, request, db)
        write_audit(
            db,
            principal=principal,
            action="strategy.update",
            resource_type="opportunity",
            resource_id=opportunity_id,
            request=http_request,
        )
        db.commit()
        complete_operation(db, handle, result.model_dump(mode="json"))
        return result
    except ValueError as exc:
        fail_operation(db, handle, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        fail_operation(db, handle, type(exc).__name__)
        raise


@app.post("/api/opportunities/{opportunity_id}/strategy/generate", deprecated=True)
async def pursuit_strategy_generate(
    opportunity_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    _inline_only(f"/api/jobs/opportunities/{opportunity_id}/strategy/generate")
    item = get_opportunity(opportunity_id, db)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    draft, mode = await generate_strategy(item)
    return {"mode": mode, "draft": draft}


@app.post("/api/opportunities/{opportunity_id}/strategy/red-team", deprecated=True)
async def pursuit_strategy_red_team(
    opportunity_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    _inline_only(f"/api/jobs/opportunities/{opportunity_id}/strategy/red-team")
    item = get_opportunity(opportunity_id, db)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    workspace = get_strategy(opportunity_id, db)
    challenge, mode = await red_team(item, workspace.strategy)
    return {"mode": mode, "challenge": challenge}


@app.post("/api/opportunities/{opportunity_id}/analyze", deprecated=True)
async def analyze_opportunity(
    opportunity_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    _inline_only(f"/api/jobs/opportunities/{opportunity_id}/analyze")
    item = get_opportunity(opportunity_id, db)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    analysis, mode = await AIService().analyze(item)
    return {
        "mode": mode,
        "opportunity_id": item.id,
        "analysis": AnalysisResult.model_validate(analysis),
    }

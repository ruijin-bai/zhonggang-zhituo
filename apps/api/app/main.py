import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .ai import AIService
from .config import get_settings
from .db import get_db
from .discovery import confirm_draft, discover
from .ingestion import ingest_source
from .models import AnalysisResult, ConfirmDraftRequest, ConfirmDraftResult, DiscoverRequest, DiscoverResult, IngestResult, Opportunity, SourceIngestRequest
from .radar import BatchScanRequest, BatchScanResult, RadarOverview, batch_scan, get_radar
from .repository import get_opportunity, list_opportunities
from .scoring import calculate_score
from .strategy import StrategyUpsert, StrategyWorkspace, get_strategy, save_strategy
from .tracking import ActionCreate, TrackingBoard, WatchUpsert, add_action, complete_action, get_tracking_board, resolve_alert, watch_opportunity

settings = get_settings()
app = FastAPI(title="中港智拓 API", version="0.6.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok", "service": "zhituo-api", "version": "0.6.0"}

@app.get("/api/meta")
def meta() -> dict: return {"version": "0.6.0", "data_backend": settings.data_backend, "ai_enabled": settings.ai_enabled, "ai_extraction_model": settings.ai_model_extraction if settings.ai_enabled else None, "ai_analysis_model": settings.ai_model_analysis if settings.ai_enabled else None}

@app.get("/api/opportunities", response_model=list[Opportunity])
def opportunities(db: Session = Depends(get_db)) -> list[Opportunity]: return list_opportunities(db)

@app.get("/api/opportunities/{opportunity_id}", response_model=Opportunity)
def opportunity_detail(opportunity_id: str, db: Session = Depends(get_db)) -> Opportunity:
    item = get_opportunity(opportunity_id, db)
    if not item: raise HTTPException(status_code=404, detail="Opportunity not found")
    return item

@app.get("/api/opportunities/{opportunity_id}/score")
def opportunity_score(opportunity_id: str, db: Session = Depends(get_db)) -> dict:
    item = get_opportunity(opportunity_id, db)
    if not item: raise HTTPException(status_code=404, detail="Opportunity not found")
    result = calculate_score(item.breakdown, item.confidence)
    return {"opportunity_id": item.id, "total": result.total, "grade": result.grade, "decision": result.decision, "confidence": item.confidence, "breakdown": item.breakdown}

@app.get("/api/radar", response_model=RadarOverview)
def market_radar(db: Session = Depends(get_db)) -> RadarOverview: return get_radar(db)

@app.post("/api/discovery/batch", response_model=BatchScanResult)
async def discovery_batch(request: BatchScanRequest, db: Session = Depends(get_db)) -> BatchScanResult: return await batch_scan(request, db)

@app.post("/api/sources/ingest", response_model=IngestResult)
async def source_ingest(request: SourceIngestRequest, db: Session = Depends(get_db)) -> IngestResult: return await ingest_source(request, db)

@app.post("/api/discovery/scan", response_model=DiscoverResult)
async def discovery_scan(request: DiscoverRequest, db: Session = Depends(get_db)) -> DiscoverResult:
    try: return await discover(request, db)
    except (ValueError, httpx.HTTPError) as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/discovery/drafts/{draft_id}/confirm", response_model=ConfirmDraftResult)
def discovery_confirm(draft_id: str, request: ConfirmDraftRequest, db: Session = Depends(get_db)) -> ConfirmDraftResult:
    try: return confirm_draft(draft_id, request, db)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/tracking", response_model=TrackingBoard)
def tracking_board(db: Session = Depends(get_db)) -> TrackingBoard: return get_tracking_board(db)

@app.put("/api/tracking/{opportunity_id}/watch")
def tracking_watch(opportunity_id: str, request: WatchUpsert, db: Session = Depends(get_db)) -> dict:
    try: return watch_opportunity(opportunity_id, request, db)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/tracking/{opportunity_id}/actions")
def tracking_add_action(opportunity_id: str, request: ActionCreate, db: Session = Depends(get_db)) -> dict:
    try: return add_action(opportunity_id, request, db)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/tracking/actions/{action_id}/complete")
def tracking_complete_action(action_id: int, db: Session = Depends(get_db)) -> dict:
    try: return complete_action(action_id, db)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/tracking/alerts/{alert_id}/resolve")
def tracking_resolve_alert(alert_id: int, db: Session = Depends(get_db)) -> dict:
    try: return resolve_alert(alert_id, db)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get("/api/opportunities/{opportunity_id}/strategy", response_model=StrategyWorkspace)
def pursuit_strategy(opportunity_id: str, db: Session = Depends(get_db)) -> StrategyWorkspace:
    try: return get_strategy(opportunity_id, db)
    except ValueError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.put("/api/opportunities/{opportunity_id}/strategy", response_model=StrategyWorkspace)
def pursuit_strategy_update(opportunity_id: str, request: StrategyUpsert, db: Session = Depends(get_db)) -> StrategyWorkspace:
    try: return save_strategy(opportunity_id, request, db)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/opportunities/{opportunity_id}/analyze")
async def analyze_opportunity(opportunity_id: str, db: Session = Depends(get_db)) -> dict:
    item = get_opportunity(opportunity_id, db)
    if not item: raise HTTPException(status_code=404, detail="Opportunity not found")
    analysis, mode = await AIService().analyze(item)
    return {"mode": mode, "opportunity_id": item.id, "analysis": AnalysisResult.model_validate(analysis)}

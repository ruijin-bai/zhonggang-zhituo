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
from .repository import get_opportunity, list_opportunities
from .scoring import calculate_score

settings = get_settings()
app = FastAPI(title="中港智拓 API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "zhituo-api", "version": "0.3.0"}


@app.get("/api/meta")
def meta() -> dict:
    return {"version": "0.3.0", "data_backend": settings.data_backend, "ai_enabled": settings.ai_enabled, "ai_extraction_model": settings.ai_model_extraction if settings.ai_enabled else None, "ai_analysis_model": settings.ai_model_analysis if settings.ai_enabled else None}


@app.get("/api/opportunities", response_model=list[Opportunity])
def opportunities(db: Session = Depends(get_db)) -> list[Opportunity]:
    return list_opportunities(db)


@app.get("/api/opportunities/{opportunity_id}", response_model=Opportunity)
def opportunity_detail(opportunity_id: str, db: Session = Depends(get_db)) -> Opportunity:
    item = get_opportunity(opportunity_id, db)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return item


@app.get("/api/opportunities/{opportunity_id}/score")
def opportunity_score(opportunity_id: str, db: Session = Depends(get_db)) -> dict:
    item = get_opportunity(opportunity_id, db)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    result = calculate_score(item.breakdown, item.confidence)
    return {"opportunity_id": item.id, "total": result.total, "grade": result.grade, "decision": result.decision, "confidence": item.confidence, "breakdown": item.breakdown}


@app.post("/api/sources/ingest", response_model=IngestResult)
async def source_ingest(request: SourceIngestRequest, db: Session = Depends(get_db)) -> IngestResult:
    return await ingest_source(request, db)


@app.post("/api/discovery/scan", response_model=DiscoverResult)
async def discovery_scan(request: DiscoverRequest, db: Session = Depends(get_db)) -> DiscoverResult:
    try:
        return await discover(request, db)
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/discovery/drafts/{draft_id}/confirm", response_model=ConfirmDraftResult)
def discovery_confirm(draft_id: str, request: ConfirmDraftRequest, db: Session = Depends(get_db)) -> ConfirmDraftResult:
    try:
        return confirm_draft(draft_id, request, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/opportunities/{opportunity_id}/analyze")
async def analyze_opportunity(opportunity_id: str, db: Session = Depends(get_db)) -> dict:
    item = get_opportunity(opportunity_id, db)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    analysis, mode = await AIService().analyze(item)
    return {"mode": mode, "opportunity_id": item.id, "analysis": AnalysisResult.model_validate(analysis)}

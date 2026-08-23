from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .models import Opportunity
from .repository import get_opportunity, load_opportunities
from .scoring import calculate_score

app = FastAPI(title="中港智拓 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "zhituo-api", "version": "0.1.0"}

@app.get("/api/opportunities", response_model=list[Opportunity])
def list_opportunities() -> list[Opportunity]:
    return load_opportunities()

@app.get("/api/opportunities/{opportunity_id}", response_model=Opportunity)
def opportunity_detail(opportunity_id: str) -> Opportunity:
    item = get_opportunity(opportunity_id)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return item

@app.get("/api/opportunities/{opportunity_id}/score")
def opportunity_score(opportunity_id: str) -> dict:
    item = get_opportunity(opportunity_id)
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

@app.post("/api/opportunities/{opportunity_id}/analyze")
def analyze_opportunity(opportunity_id: str) -> dict:
    item = get_opportunity(opportunity_id)
    if not item:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return {
        "mode": "deterministic-baseline",
        "opportunity_id": item.id,
        "conclusion": item.pursuit_thesis,
        "next_actions": item.next_actions,
        "note": "AI Provider 将在下一阶段接入；当前接口先固定结构化输出契约。",
    }

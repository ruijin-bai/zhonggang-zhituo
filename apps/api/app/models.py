from typing import Literal
from pydantic import BaseModel, Field

Grade = Literal["A", "B", "C", "D"]
Decision = Literal["GO", "WATCH", "CAUTION", "NO-GO", "INSUFFICIENT_EVIDENCE"]

class ScoreBreakdown(BaseModel):
    strategic_fit: int = Field(ge=0, le=20)
    project_maturity: int = Field(ge=0, le=15)
    financing: int = Field(ge=0, le=15)
    client_quality: int = Field(ge=0, le=10)
    capability_fit: int = Field(ge=0, le=15)
    local_position: int = Field(ge=0, le=10)
    competition: int = Field(ge=0, le=10)
    risk_control: int = Field(ge=0, le=5)

class Evidence(BaseModel):
    id: str
    rank: Literal["S", "A", "B", "C", "D"]
    title: str
    publisher: str
    published_at: str
    fact: str

class ScoreSnapshot(BaseModel):
    date: str
    total: int
    grade: Grade
    note: str

class Opportunity(BaseModel):
    id: str
    title: str
    country: str
    region: str
    sector: str
    stage: str
    owner: str
    estimated_value_usd_m: float | None = None
    summary: str
    score: int = Field(ge=0, le=100)
    grade: Grade
    confidence: int = Field(ge=0, le=100)
    decision: Decision
    breakdown: ScoreBreakdown
    evidence: list[Evidence] = []
    score_history: list[ScoreSnapshot] = []
    pursuit_thesis: str
    next_actions: list[str] = []
    is_demo: bool = True

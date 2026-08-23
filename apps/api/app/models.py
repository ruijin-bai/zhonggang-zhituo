from typing import Literal

from pydantic import BaseModel, Field

Grade = Literal["A", "B", "C", "D"]
Decision = Literal["GO", "WATCH", "CAUTION", "NO-GO", "INSUFFICIENT_EVIDENCE"]
SourceRank = Literal["S", "A", "B", "C", "D"]
ScoreField = Literal[
    "strategic_fit",
    "project_maturity",
    "financing",
    "client_quality",
    "capability_fit",
    "local_position",
    "competition",
    "risk_control",
]


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
    rank: SourceRank
    title: str
    publisher: str
    published_at: str
    fact: str
    field_name: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    source_url: str | None = None


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
    evidence: list[Evidence] = Field(default_factory=list)
    score_history: list[ScoreSnapshot] = Field(default_factory=list)
    pursuit_thesis: str
    next_actions: list[str] = Field(default_factory=list)
    is_demo: bool = True


class ExtractedFact(BaseModel):
    field_name: ScoreField
    value: str
    score_hint: int | None = None
    evidence_quote: str
    confidence: float = Field(ge=0, le=1)


class SourceExtraction(BaseModel):
    project_detected: bool = True
    summary: str
    facts: list[ExtractedFact] = Field(default_factory=list)


class SourceIngestRequest(BaseModel):
    opportunity_id: str | None = None
    title: str
    publisher: str
    published_at: str
    source_rank: SourceRank = "B"
    url: str | None = None
    text: str = Field(min_length=20, max_length=100_000)
    use_ai: bool = True
    is_demo: bool = True


class IngestResult(BaseModel):
    opportunity_id: str | None
    persisted: bool
    extraction_mode: Literal["ai", "deterministic"]
    extraction: SourceExtraction
    score_before: int | None = None
    score_after: int | None = None
    grade_before: Grade | None = None
    grade_after: Grade | None = None
    decision_after: Decision | None = None
    applied_fields: list[str] = Field(default_factory=list)
    note: str


class AnalysisResult(BaseModel):
    conclusion: str
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)

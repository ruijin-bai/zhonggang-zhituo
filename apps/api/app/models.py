from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
ProjectPartyRole = Literal["owner", "financier", "competitor", "partner"]


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


class ProjectParty(BaseModel):
    role: ProjectPartyRole
    name: str = Field(min_length=2, max_length=320)
    country: str | None = Field(default=None, max_length=120)
    evidence_quote: str = Field(default="", max_length=1000)
    confidence: float = Field(default=1.0, ge=0, le=1)


class ProjectDiscovery(BaseModel):
    project_detected: bool
    title: str
    country: str = "待识别"
    region: str = "待识别"
    sector: str = "待识别"
    stage: str = "待核实"
    owner: str = "待识别"
    estimated_value_usd_m: float | None = None
    summary: str
    confidence: float = Field(ge=0, le=1)
    facts: list[ExtractedFact] = Field(default_factory=list)
    parties: list[ProjectParty] = Field(default_factory=list)


class DiscoverRequest(BaseModel):
    url: str | None = None
    text: str | None = Field(default=None, max_length=100_000)
    source_title: str | None = None
    publisher: str = "公开来源"
    published_at: str = "待核实"
    source_rank: SourceRank = "B"
    use_ai: bool = True
    is_demo: bool = False

    @model_validator(mode="after")
    def require_url_or_text(self):
        if not self.url and not (self.text and self.text.strip()):
            raise ValueError("url 和 text 至少提供一个")
        return self


class DuplicateMatch(BaseModel):
    opportunity_id: str
    title: str
    country: str
    similarity: float = Field(ge=0, le=1)


class DraftOpportunity(BaseModel):
    id: str
    status: Literal["pending", "confirmed", "rejected"] = "pending"
    discovery: ProjectDiscovery
    source_url: str | None = None
    source_title: str
    publisher: str
    published_at: str
    source_rank: SourceRank
    duplicate_matches: list[DuplicateMatch] = Field(default_factory=list)
    persisted: bool


class DiscoverResult(BaseModel):
    mode: Literal["ai", "deterministic"]
    draft: DraftOpportunity
    note: str


class ConfirmDraftRequest(BaseModel):
    title: str | None = None
    country: str | None = None
    region: str | None = None
    sector: str | None = None
    stage: str | None = None
    owner: str | None = None
    estimated_value_usd_m: float | None = None
    summary: str | None = None


class ConfirmDraftResult(BaseModel):
    opportunity: Opportunity
    source_bound: bool
    note: str

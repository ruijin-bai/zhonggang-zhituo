from dataclasses import dataclass
from .models import ScoreBreakdown

@dataclass(frozen=True)
class ScoreResult:
    total: int
    grade: str
    decision: str


def grade_for(total: int) -> str:
    if total >= 80:
        return "A"
    if total >= 65:
        return "B"
    if total >= 50:
        return "C"
    return "D"


def decision_for(total: int, confidence: int, blockers: list[str] | None = None) -> str:
    blockers = blockers or []
    if blockers:
        return "NO-GO"
    if confidence < 45:
        return "INSUFFICIENT_EVIDENCE"
    if total >= 80:
        return "GO"
    if total >= 65:
        return "WATCH"
    if total >= 50:
        return "CAUTION"
    return "NO-GO"


def calculate_score(breakdown: ScoreBreakdown, confidence: int, blockers: list[str] | None = None) -> ScoreResult:
    total = sum(breakdown.model_dump().values())
    return ScoreResult(total=total, grade=grade_for(total), decision=decision_for(total, confidence, blockers))

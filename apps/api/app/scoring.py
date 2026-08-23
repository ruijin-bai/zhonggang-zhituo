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


def calculate_score(
    breakdown: ScoreBreakdown,
    confidence: int,
    blockers: list[str] | None = None,
) -> ScoreResult:
    total = sum(breakdown.model_dump().values())
    return ScoreResult(
        total=total,
        grade=grade_for(total),
        decision=decision_for(total, confidence, blockers),
    )


def apply_score_updates(
    breakdown: ScoreBreakdown,
    updates: dict[str, int],
) -> tuple[ScoreBreakdown, list[str]]:
    values = breakdown.model_dump()
    applied: list[str] = []
    limits = {
        "strategic_fit": 20,
        "project_maturity": 15,
        "financing": 15,
        "client_quality": 10,
        "capability_fit": 15,
        "local_position": 10,
        "competition": 10,
        "risk_control": 5,
    }
    for field_name, new_value in updates.items():
        if field_name not in limits:
            continue
        normalized = max(0, min(limits[field_name], int(new_value)))
        if normalized != values[field_name]:
            values[field_name] = normalized
            applied.append(field_name)
    return ScoreBreakdown.model_validate(values), applied

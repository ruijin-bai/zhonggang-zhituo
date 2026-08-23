from app.models import ScoreBreakdown
from app.scoring import calculate_score


def test_persistent_hero_baseline_is_72_b() -> None:
    baseline = ScoreBreakdown(
        strategic_fit=18,
        project_maturity=11,
        financing=8,
        client_quality=8,
        capability_fit=13,
        local_position=7,
        competition=4,
        risk_control=3,
    )
    result = calculate_score(baseline, confidence=86)
    assert result.total == 72
    assert result.grade == "B"
    assert result.decision == "WATCH"

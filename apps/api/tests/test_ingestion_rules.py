from app.models import ScoreBreakdown
from app.scoring import apply_score_updates, calculate_score


def test_hero_score_change_is_reproducible() -> None:
    before = ScoreBreakdown(
        strategic_fit=18,
        project_maturity=11,
        financing=8,
        client_quality=8,
        capability_fit=13,
        local_position=7,
        competition=4,
        risk_control=3,
    )
    assert calculate_score(before, confidence=86).total == 72
    after, applied = apply_score_updates(before, {"financing": 15, "project_maturity": 13})
    result = calculate_score(after, confidence=86)
    assert result.total == 81
    assert result.grade == "A"
    assert result.decision == "GO"
    assert set(applied) == {"financing", "project_maturity"}

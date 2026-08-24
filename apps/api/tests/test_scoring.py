from app.models import ScoreBreakdown
from app.scoring import calculate_score, decision_for, grade_for


def test_grade_boundaries():
    assert grade_for(80) == "A"
    assert grade_for(65) == "B"
    assert grade_for(50) == "C"
    assert grade_for(49) == "D"


def test_hero_score_is_81_and_go():
    breakdown = ScoreBreakdown(
        strategic_fit=18,
        project_maturity=13,
        financing=15,
        client_quality=8,
        capability_fit=13,
        local_position=7,
        competition=4,
        risk_control=3,
    )
    result = calculate_score(breakdown, confidence=86)
    assert result.total == 81
    assert result.grade == "A"
    assert result.decision == "GO"


def test_low_confidence_does_not_force_go():
    assert decision_for(88, confidence=40) == "INSUFFICIENT_EVIDENCE"


def test_blocker_overrides_high_score():
    assert decision_for(90, confidence=95, blockers=["重大合规阻断项"]) == "NO-GO"

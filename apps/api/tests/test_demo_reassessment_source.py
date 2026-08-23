import json
from pathlib import Path

from app.extraction import extract_facts_deterministic
from app.models import ScoreBreakdown
from app.scoring import apply_score_updates, calculate_score


SOURCE = Path(__file__).resolve().parents[3] / "data" / "demo" / "hero_reassessment_source.json"


def test_hero_reassessment_source_reproduces_expected_score() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    extraction = extract_facts_deterministic(payload["text"])
    updates = {fact.field_name: fact.score_hint for fact in extraction.facts if fact.score_hint is not None}

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
    before = calculate_score(baseline, confidence=86)
    after_breakdown, applied = apply_score_updates(baseline, updates)
    after = calculate_score(after_breakdown, confidence=86)

    expected = payload["expected_result"]
    assert before.total == expected["score_before"]
    assert before.grade == expected["grade_before"]
    assert after.total == expected["score_after"]
    assert after.grade == expected["grade_after"]
    assert after.decision == expected["decision_after"]
    assert set(applied) == set(expected["applied_fields"])

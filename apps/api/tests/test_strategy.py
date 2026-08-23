from app.models import Opportunity, ScoreBreakdown
from app.strategy import _readiness
from app.strategy_ai import deterministic_red_team


def _opportunity() -> Opportunity:
    return Opportunity(
        id="demo",
        title="Demo",
        country="Nigeria",
        region="West Africa",
        sector="Road",
        stage="Procurement",
        owner="Owner",
        summary="Port access corridor",
        score=81,
        grade="A",
        confidence=66,
        decision="GO",
        breakdown=ScoreBreakdown(strategic_fit=18, project_maturity=13, financing=15, client_quality=8, capability_fit=13, local_position=7, competition=4, risk_control=3),
        pursuit_thesis="Integrated delivery can reduce interface risk.",
        next_actions=["Verify procurement criteria"],
    )


def test_readiness_penalizes_missing_competition_and_decision_chain() -> None:
    score, warnings = _readiness({"win_theme":"A","client_need":"B","differentiation":["C"],"gaps":[],"competitors":[],"stakeholders":[],"next_moves":["D"]})
    assert score < 80
    assert "竞争对手画像为空" in warnings
    assert "客户决策链尚未建立" in warnings


def test_red_team_surfaces_missing_evidence_without_inventing_entities() -> None:
    result = deterministic_red_team(_opportunity(), {"competitors":[], "stakeholders":[]})
    joined = " ".join(result.missing_evidence)
    assert "竞争对手" in joined
    assert "客户决策链" in joined
    assert result.counter_moves

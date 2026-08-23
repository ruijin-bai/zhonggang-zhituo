from app.models import Opportunity, ScoreBreakdown
from app.radar import build_radar


def opportunity(id_: str, country: str, score: int, grade: str, confidence: int, sector: str = "港口工程") -> Opportunity:
    return Opportunity(
        id=id_, title=id_, country=country, region="西非", sector=sector, stage="采购准备",
        owner="Owner", estimated_value_usd_m=100, summary="summary", score=score, grade=grade,
        confidence=confidence, decision="GO" if grade == "A" else "WATCH",
        breakdown=ScoreBreakdown(strategic_fit=18, project_maturity=13, financing=15, client_quality=8, capability_fit=13, local_position=7, competition=4, risk_control=3),
        pursuit_thesis="thesis", next_actions=[], is_demo=True,
    )


def test_radar_separates_activity_from_attractiveness() -> None:
    items = [
        opportunity("n1", "Nigeria", 81, "A", 86),
        opportunity("n2", "Nigeria", 72, "B", 75, "公路工程"),
        opportunity("g1", "Ghana", 20, "D", 30),
    ]
    radar = build_radar(
        items,
        drafts=[{"country": "Ghana", "region": "西非", "sector": "港口工程"}],
        sources_by_country={"Nigeria": 4, "Ghana": 1},
        evidence_by_country={"Nigeria": 6},
        source_count=5,
        evidence_count=6,
    )
    nigeria = next(item for item in radar.countries if item.country == "Nigeria")
    ghana = next(item for item in radar.countries if item.country == "Ghana")
    assert nigeria.attractiveness_index is not None
    assert nigeria.high_grade_count == 1
    assert ghana.activity_index > 0
    assert ghana.attractiveness_index is None

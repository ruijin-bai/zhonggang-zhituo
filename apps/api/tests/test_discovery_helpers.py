from app.discovery import _initial_breakdown
from app.models import ExtractedFact, ProjectDiscovery


def test_discovery_initial_score_only_uses_supported_facts() -> None:
    discovery = ProjectDiscovery(
        project_detected=True,
        title="Demo Corridor",
        country="Nigeria",
        region="West Africa",
        sector="Road",
        stage="Procurement preparation",
        owner="Demo Owner",
        summary="Demo",
        confidence=0.9,
        facts=[
            ExtractedFact(field_name="financing", value="approved", score_hint=15, evidence_quote="loan approved", confidence=0.96),
            ExtractedFact(field_name="project_maturity", value="procurement", score_hint=13, evidence_quote="procurement plan", confidence=0.92),
            ExtractedFact(field_name="strategic_fit", value="guess", score_hint=20, evidence_quote="weak", confidence=0.4),
        ],
    )
    breakdown = _initial_breakdown(discovery)
    assert breakdown.financing == 15
    assert breakdown.project_maturity == 13
    assert breakdown.strategic_fit == 0

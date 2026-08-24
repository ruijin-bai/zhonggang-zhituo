from app.ai import _deterministic_project
from app.discovery import _initial_breakdown
from app.models import ExtractedFact, ProjectDiscovery


def _discovery(facts: list[ExtractedFact]) -> ProjectDiscovery:
    return ProjectDiscovery(
        project_detected=True,
        title="Demo Corridor",
        country="Nigeria",
        region="West Africa",
        sector="Road",
        stage="Procurement preparation",
        owner="Demo Owner",
        summary="Demo",
        confidence=0.9,
        facts=facts,
    )


def test_discovery_initial_score_only_uses_supported_facts() -> None:
    discovery = _discovery(
        [
            ExtractedFact(field_name="financing", value="approved", score_hint=15, evidence_quote="loan approved", confidence=0.96),
            ExtractedFact(field_name="project_maturity", value="procurement", score_hint=13, evidence_quote="procurement plan", confidence=0.92),
            ExtractedFact(field_name="strategic_fit", value="guess", score_hint=20, evidence_quote="weak", confidence=0.4),
        ]
    )
    breakdown = _initial_breakdown([discovery])
    assert breakdown.financing == 15
    assert breakdown.project_maturity == 13
    assert breakdown.strategic_fit == 0


def test_multi_source_initial_score_uses_strongest_supported_fact_per_dimension() -> None:
    first = _discovery(
        [
            ExtractedFact(
                field_name="financing",
                value="proposed",
                score_hint=8,
                evidence_quote="proposed financing",
                confidence=0.9,
            )
        ]
    )
    second = _discovery(
        [
            ExtractedFact(
                field_name="financing",
                value="approved",
                score_hint=15,
                evidence_quote="financing approved",
                confidence=0.95,
            )
        ]
    )
    assert _initial_breakdown([first, second]).financing == 15


def test_deterministic_project_extracts_only_explicit_project_parties() -> None:
    text = (
        "Nigeria port expansion project. Owner: Nigerian Ports Authority. "
        "Financier: World Bank. Consortium with Atlantic Engineering Ltd."
    )
    discovery = _deterministic_project(text, "Lagos Port Expansion")
    parties = {(item.role, item.name) for item in discovery.parties}
    assert ("owner", "Nigerian Ports Authority") in parties
    assert ("financier", "World Bank") in parties
    assert ("partner", "Atlantic Engineering Ltd") in parties
    assert not any(role == "competitor" for role, _ in parties)

from app.extraction import extract_facts_deterministic


def test_extract_financing_and_procurement_upgrade() -> None:
    text = (
        "The board approved the loan for the corridor project. "
        "The owner also published its procurement plan for the works."
    )
    extraction = extract_facts_deterministic(text)
    by_field = {fact.field_name: fact for fact in extraction.facts}
    assert by_field["financing"].score_hint == 15
    assert by_field["project_maturity"].score_hint == 13
    assert by_field["financing"].confidence >= 0.9


def test_no_unsupported_fact_is_invented() -> None:
    extraction = extract_facts_deterministic(
        "The project was discussed at an industry conference, with no financing details disclosed."
    )
    assert extraction.facts == []

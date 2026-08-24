import json
from pathlib import Path

from app.ai import _deterministic_project
from app.extraction import extract_facts_deterministic

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "public_samples" / "afdb_abia_roads_2026.json"


def test_verified_public_sample_is_detected_as_project() -> None:
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    text = payload["safe_demo_text"]
    result = _deterministic_project(text, payload["project"]["name"])
    assert result.project_detected is True
    assert result.country in {"Nigeria", "尼日利亚"}
    assert result.sector == "公路工程"


def test_verified_public_sample_extracts_procurement_and_financing_signals() -> None:
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    extraction = extract_facts_deterministic(payload["safe_demo_text"])
    fields = {fact.field_name for fact in extraction.facts}
    assert "financing" in fields
    assert "project_maturity" in fields


def test_public_sample_explicitly_excludes_private_assumptions() -> None:
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    note = payload["usage_note"].lower()
    assert "bid probability" in note
    assert "private client preferences" in note

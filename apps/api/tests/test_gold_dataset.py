import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data" / "benchmark" / "gold_dataset.json"


def test_gold_dataset_has_ten_official_samples():
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    assert len(rows) >= 10
    assert all(row["source_url"].startswith("https://www.afdb.org/") for row in rows)
    assert all(row["country"] and row["sector"] and row["title"] for row in rows)


def test_gold_dataset_marks_non_public_business_inferences():
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    for row in rows:
        forbidden = " ".join(row["must_not_infer"]).lower()
        assert any(term in forbidden for term in ("preference", "probability", "preferred", "competitor", "relationship", "winner", "bidder"))


def test_gold_dataset_has_traceable_evidence():
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    assert all(len(row["gold_evidence"]) >= 1 for row in rows)

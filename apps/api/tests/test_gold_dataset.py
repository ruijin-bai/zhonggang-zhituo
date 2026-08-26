from copy import deepcopy
from pathlib import Path

import pytest

from app.gold_dataset import (
    is_known_aggregate_listing,
    load_gold_dataset,
    normalize_source_url,
    validate_gold_dataset,
)

ROOT = Path(__file__).resolve().parents[3]


def test_full_gold_dataset_has_thirteen_official_samples():
    rows = load_gold_dataset(ROOT, include_extensions=True)
    validation = validate_gold_dataset(rows)

    assert validation.samples == 13
    assert validation.positives == 13
    assert all(row["source_url"].startswith("https://www.afdb.org/") for row in rows)
    assert all(row["country"] and row["sector"] and row["title"] for row in rows)


def test_gold_dataset_marks_non_public_business_inferences():
    rows = load_gold_dataset(ROOT, include_extensions=True)
    for row in rows:
        forbidden = " ".join(row["must_not_infer"]).lower()
        assert any(
            term in forbidden
            for term in (
                "preference",
                "probability",
                "preferred",
                "competitor",
                "relationship",
                "winner",
                "bidder",
            )
        )


def test_gold_dataset_has_traceable_evidence():
    rows = load_gold_dataset(ROOT, include_extensions=True)
    assert all(len(row["gold_evidence"]) >= 1 for row in rows)


def test_gold_sources_are_unique_one_to_one_documents():
    rows = load_gold_dataset(ROOT, include_extensions=True)
    urls = [normalize_source_url(row["source_url"]) for row in rows]

    assert len(urls) == len(set(urls))
    assert all(not is_known_aggregate_listing(row["source_url"]) for row in rows)


def test_validation_rejects_duplicate_positive_source_url():
    rows = load_gold_dataset(ROOT, include_extensions=True)
    broken = deepcopy(rows)
    broken[1]["source_url"] = broken[0]["source_url"] + "#fragment"

    with pytest.raises(ValueError, match="duplicate positive source_url"):
        validate_gold_dataset(broken)


def test_validation_rejects_afdb_aggregate_listing():
    rows = load_gold_dataset(ROOT, include_extensions=True)
    broken = deepcopy(rows)
    broken[0]["source_url"] = (
        "https://www.afdb.org/en/documents/project-related-procurement/"
        "procurement-notices/specific-procurement-notices"
    )

    with pytest.raises(ValueError, match="aggregate listing"):
        validate_gold_dataset(broken)

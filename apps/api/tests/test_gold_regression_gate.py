from pathlib import Path

from app.evaluation_runner import evaluate_pipeline_sync
from app.gold_dataset import load_gold_dataset, validate_gold_dataset

ROOT = Path(__file__).resolve().parents[3]


def test_gold_fixture_regression_floor() -> None:
    """Required CI regression floor; fixture scores are never business-accuracy claims."""
    samples = load_gold_dataset(
        ROOT,
        include_extensions=True,
        include_regression_negatives=True,
    )
    dataset = validate_gold_dataset(samples)
    report = evaluate_pipeline_sync(samples, input_mode="fixture", use_ai=False)
    summary = report.summary

    assert dataset.positives >= 13
    assert dataset.negatives >= 4
    assert report.mode == "fixture"
    assert report.publishable is False
    assert report.samples_skipped == 0
    assert report.samples_evaluated == report.samples_total

    # Conservative initial ratchet. These are engineering regression floors, not published KPIs.
    assert summary["detection_accuracy_pct"] == 100.0
    assert summary["field_accuracy_pct"] >= 60.0
    assert summary["evidence_recall_pct"] >= 10.0
    assert summary["safety_pass_pct"] == 100.0

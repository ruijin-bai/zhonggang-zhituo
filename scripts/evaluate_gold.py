#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.evaluation import evaluate_sample, report_dict  # noqa: E402
from app.gold_dataset import load_gold_dataset, validate_gold_dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", default="data/benchmark/predictions.json")
    parser.add_argument("--output", default="data/benchmark/evaluation_report.json")
    args = parser.parse_args()

    gold = load_gold_dataset(ROOT, include_extensions=True)
    validate_gold_dataset(gold)
    pred_path = ROOT / args.predictions
    if not pred_path.exists():
        print(
            f"No predictions found: {pred_path}\n"
            "Run the extraction pipeline and save structured predictions before evaluation. "
            "No score has been fabricated."
        )
        return
    predictions = {
        item["sample_id"]: item
        for item in json.loads(pred_path.read_text(encoding="utf-8"))
    }
    results = [
        evaluate_sample(sample, predictions[sample["sample_id"]])
        for sample in gold
        if sample["sample_id"] in predictions
    ]
    report = report_dict(results)
    out = ROOT / args.output
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = report["summary"]
    print(
        f"Samples: {summary['samples']} | "
        f"Detection: {summary['detection_accuracy_pct']}% | "
        f"Field accuracy: {summary['field_accuracy_pct']}% | "
        f"Evidence recall: {summary['evidence_recall_pct']}% | "
        f"Safety pass: {summary['safety_pass_pct']}%"
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce Zhituo Gold fixture regression floor")
    parser.add_argument("--report", default="data/benchmark/ci_evaluation.json")
    parser.add_argument("--min-detection", type=float, default=100.0)
    parser.add_argument("--min-fields", type=float, default=60.0)
    parser.add_argument("--min-evidence", type=float, default=10.0)
    parser.add_argument("--min-safety", type=float, default=100.0)
    parser.add_argument("--min-positive-samples", type=int, default=13)
    parser.add_argument("--min-negative-samples", type=int, default=4)
    args = parser.parse_args()

    path = ROOT / args.report
    report = json.loads(path.read_text(encoding="utf-8"))
    summary = report["summary"]
    dataset = report["dataset"]
    failures: list[str] = []

    if report.get("mode") != "fixture":
        failures.append("CI Gold gate must consume a fixture-mode report")
    if report.get("publishable"):
        failures.append("fixture-mode report must never be marked publishable")
    if report.get("samples_skipped") != 0:
        failures.append(f"fixture regression skipped {report.get('samples_skipped')} samples")
    if dataset.get("positives", 0) < args.min_positive_samples:
        failures.append(
            f"positive Gold samples {dataset.get('positives', 0)} < {args.min_positive_samples}"
        )
    if dataset.get("negatives", 0) < args.min_negative_samples:
        failures.append(
            f"negative regression samples {dataset.get('negatives', 0)} < {args.min_negative_samples}"
        )

    metrics = {
        "detection_accuracy_pct": args.min_detection,
        "field_accuracy_pct": args.min_fields,
        "evidence_recall_pct": args.min_evidence,
        "safety_pass_pct": args.min_safety,
    }
    for key, floor in metrics.items():
        actual = float(summary.get(key, 0.0))
        if actual < floor:
            failures.append(f"{key} {actual:.1f}% < regression floor {floor:.1f}%")

    print("Zhituo Gold regression gate")
    print(
        "samples="
        f"{report.get('samples_evaluated')}/{report.get('samples_total')} "
        f"positive={dataset.get('positives')} negative={dataset.get('negatives')}"
    )
    for key, floor in metrics.items():
        print(f"{key}={summary.get(key)}% floor={floor}%")
    print("fixture metrics are engineering regression signals only; they are not business accuracy claims")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        raise SystemExit(1)
    print("PASS: Gold regression floor satisfied")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.evaluation_runner import evaluate_pipeline_sync  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Zhituo extraction/discovery pipeline against Gold Dataset")
    parser.add_argument("--mode", choices=["fixture", "source-text"], default="source-text")
    parser.add_argument("--ai", action="store_true", help="Use configured AI provider when available")
    parser.add_argument("--output", default="data/benchmark/latest_evaluation.json")
    args = parser.parse_args()

    gold_path = ROOT / "data" / "benchmark" / "gold_dataset.json"
    samples = json.loads(gold_path.read_text(encoding="utf-8"))
    report = evaluate_pipeline_sync(samples, use_ai=args.ai, input_mode=args.mode)

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")

    print("中港智拓 Gold Pipeline Evaluation")
    print(f"输入模式: {report.mode}")
    print(f"可用于正式成绩: {'YES' if report.publishable else 'NO'}")
    print(f"总样本: {report.samples_total} | 已评测: {report.samples_evaluated} | 跳过: {report.samples_skipped}")
    print(f"运行模式分布: {report.extraction_modes}")
    summary = report.summary
    print(f"字段准确率: {summary['field_accuracy_pct']}%")
    print(f"证据召回率: {summary['evidence_recall_pct']}%")
    print(f"安全通过率: {summary['safety_pass_pct']}%")
    print(report.note)
    print(f"详细结果: {output_path.relative_to(ROOT)}")

    # Refuse to silently produce a publishable-looking score from fixture data.
    if args.mode == "fixture" and os.environ.get("CI"):
        print("CI regression fixture completed; scores above are not business claims.")


if __name__ == "__main__":
    main()

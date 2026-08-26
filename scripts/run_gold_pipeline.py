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
from app.gold_dataset import load_gold_dataset, validate_gold_dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Zhituo pipeline against Gold Dataset")
    parser.add_argument("--mode", choices=["fixture", "source-text"], default="source-text")
    parser.add_argument("--ai", action="store_true")
    parser.add_argument("--output", default="data/benchmark/latest_evaluation.json")
    args = parser.parse_args()

    include_regression_negatives = args.mode == "fixture"
    samples = load_gold_dataset(
        ROOT,
        include_extensions=True,
        include_regression_negatives=include_regression_negatives,
    )
    validation = validate_gold_dataset(samples, minimum_samples=10)
    cache = ROOT / "data" / "benchmark" / "source_cache"
    report = evaluate_pipeline_sync(
        samples,
        use_ai=args.ai,
        input_mode=args.mode,
        source_cache_dir=cache,
    )
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["dataset"] = asdict(validation)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    s = report.summary
    print("中港智拓 Gold Pipeline Evaluation")
    print(f"输入模式: {report.mode}")
    print(f"可用于正式成绩: {'YES' if report.publishable else 'NO'}")
    print(
        f"总样本: {report.samples_total} | 已评测: {report.samples_evaluated} | "
        f"跳过: {report.samples_skipped}"
    )
    print(f"运行模式分布: {report.extraction_modes}")
    if args.mode == "source-text":
        verified = sum(1 for status in report.source_provenance.values() if status == "verified-snapshot")
        print(f"来源快照验证: {verified}/{report.samples_total}")
    print(f"项目识别准确率: {s['detection_accuracy_pct']}%")
    print(f"字段准确率: {s['field_accuracy_pct']}%")
    print(f"证据召回率: {s['evidence_recall_pct']}%")
    print(f"安全通过率: {s['safety_pass_pct']}%")
    print(report.note)
    print(f"详细结果: {out.relative_to(ROOT)}")
    if args.mode == "fixture" and os.environ.get("CI"):
        print("CI regression fixture completed; scores above are engineering regression signals, not business claims.")
    if args.mode == "source-text" and not report.publishable:
        print(
            "提示: source-text 正式评测要求 13/13 来源快照通过 URL、正文 SHA-256 和 Gold evidence 校验。"
        )


if __name__ == "__main__":
    main()

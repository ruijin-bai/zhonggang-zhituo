#!/usr/bin/env python3
import csv
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.benchmark import calculate_benchmark  # noqa: E402


def main() -> None:
    path = ROOT / "data" / "benchmark" / "benchmark_results.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    normalized = []
    for row in rows:
        normalized.append({
            **row,
            "decision_match": row["decision_match"].strip().lower() == "true",
        })
    metrics = calculate_benchmark(normalized)
    print("中港智拓业务价值 Benchmark")
    print(f"样本数: {metrics.samples}")
    if not metrics.samples:
        print("尚无真实测试结果；不得生成效率提升宣传数字。")
        return
    labels = {
        "manual_minutes": "人工总耗时(分钟)",
        "zhituo_minutes": "智拓总耗时(分钟)",
        "time_saved_minutes": "节省时间(分钟)",
        "efficiency_gain_pct": "效率提升(%)",
        "field_precision_pct": "字段准确率(%)",
        "evidence_traceability_pct": "证据可追溯率(%)",
        "decision_agreement_pct": "经营判断一致率(%)",
    }
    for key, value in asdict(metrics).items():
        if key != "samples":
            print(f"{labels[key]}: {value}")


if __name__ == "__main__":
    main()

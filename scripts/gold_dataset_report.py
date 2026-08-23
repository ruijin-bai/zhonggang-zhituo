#!/usr/bin/env python3
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "benchmark" / "gold_dataset.json"


def main() -> None:
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    countries = Counter(row["country"] for row in rows)
    sectors = Counter(row["sector"] for row in rows)
    stages = Counter(row["stage"] for row in rows)

    print("中港智拓 Gold Dataset Coverage")
    print(f"样本数: {len(rows)}")
    print(f"国家数: {len(countries)}")
    print("\n国家覆盖:")
    for name, count in countries.most_common():
        print(f"- {name}: {count}")
    print("\n专业覆盖:")
    for name, count in sectors.most_common():
        print(f"- {name}: {count}")
    print("\n采购阶段覆盖:")
    for name, count in stages.most_common():
        print(f"- {name}: {count}")

    forbidden = sum(len(row.get("must_not_infer", [])) for row in rows)
    evidence = sum(len(row.get("gold_evidence", [])) for row in rows)
    print(f"\n金标准证据片段数: {evidence}")
    print(f"明确禁止无证据推断项: {forbidden}")


if __name__ == "__main__":
    main()

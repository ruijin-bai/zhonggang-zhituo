#!/usr/bin/env python3
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.gold_dataset import load_gold_dataset, validate_gold_dataset  # noqa: E402


def main() -> None:
    rows = load_gold_dataset(ROOT, include_extensions=True)
    validation = validate_gold_dataset(rows)
    countries = Counter(row["country"] for row in rows if row.get("country"))
    sectors = Counter(row["sector"] for row in rows if row.get("sector"))
    stages = Counter(row["stage"] for row in rows if row.get("stage"))

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

    print(f"\n金标准证据片段数: {validation.evidence_items}")
    print(f"明确禁止无证据推断项: {validation.forbidden_claim_items}")
    print(f"Dataset contract: {asdict(validation)}")
    print("Synthetic regression negatives are intentionally excluded from real-source coverage.")


if __name__ == "__main__":
    main()

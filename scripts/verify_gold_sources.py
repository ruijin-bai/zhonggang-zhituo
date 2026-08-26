#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.gold_dataset import load_gold_dataset, validate_gold_dataset  # noqa: E402
from app.source_snapshot import verify_source_snapshot  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Gold source snapshots without network access")
    parser.add_argument(
        "--cache-dir",
        default="data/benchmark/source_cache",
        help="directory containing <sample_id>.txt source snapshots",
    )
    parser.add_argument(
        "--output",
        default="data/benchmark/source_provenance_report.json",
        help="JSON verification report path",
    )
    args = parser.parse_args()

    cache_dir = ROOT / args.cache_dir
    samples = load_gold_dataset(ROOT, include_extensions=True)
    validate_gold_dataset(samples)

    results: list[dict] = []
    content_hashes: dict[str, str] = {}
    verified = 0
    for sample in samples:
        sample_id = sample["sample_id"]
        path = cache_dir / f"{sample_id}.txt"
        if not path.exists():
            results.append({"sample_id": sample_id, "status": "missing"})
            continue
        try:
            snapshot = verify_source_snapshot(sample, path.read_text(encoding="utf-8"))
            duplicate_of = content_hashes.get(snapshot.content_sha256)
            if duplicate_of:
                raise ValueError(f"snapshot content duplicates {duplicate_of}")
            content_hashes[snapshot.content_sha256] = sample_id
            verified += 1
            results.append(
                {
                    "sample_id": sample_id,
                    "status": "verified",
                    "origin_source_url": snapshot.origin_source_url,
                    "resolved_url": snapshot.resolved_url,
                    "source_title": snapshot.source_title,
                    "fetched_at": snapshot.fetched_at,
                    "content_sha256": snapshot.content_sha256,
                    "raw_sha256": snapshot.raw_sha256,
                    "raw_size_bytes": snapshot.raw_size_bytes,
                    "char_count": len(snapshot.text),
                }
            )
        except Exception as exc:
            results.append({"sample_id": sample_id, "status": "invalid", "error": str(exc)})

    payload = {
        "samples_total": len(samples),
        "samples_verified": verified,
        "complete": verified == len(samples),
        "results": results,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Gold source provenance: {verified}/{len(samples)} verified")
    print(f"Report: {output.relative_to(ROOT)}")
    if verified != len(samples):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.connectors.pdf import PdfConnector  # noqa: E402
from app.gold_dataset import load_gold_dataset, validate_gold_dataset  # noqa: E402
from app.source_snapshot import (  # noqa: E402
    build_source_snapshot,
    evidence_coverage,
    verify_source_snapshot,
)
from app.web_fetch import MAX_PAGE_BYTES, extract_page_text, fetch_public_resource  # noqa: E402


def looks_like_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


async def fetch_sample(sample: dict) -> dict:
    sample_id = sample["sample_id"]
    url = sample["source_url"]
    fetched_at = datetime.now(timezone.utc).isoformat()

    if looks_like_pdf(url):
        result = await PdfConnector().fetch(url)
        if len(result.documents) != 1:
            raise ValueError(f"expected one PDF document, got {len(result.documents)}")
        document = result.documents[0]
        resolved_url = document.canonical_url
        title = document.title
        text = document.text
        content_type = document.content_type
        raw_sha256 = document.raw_sha256
        raw_size_bytes = document.raw_size_bytes
        source_type = "pdf"
    else:
        resource = await fetch_public_resource(
            url,
            max_bytes=MAX_PAGE_BYTES,
            accept="text/html,text/plain;q=0.9,*/*;q=0.1",
            timeout_seconds=30.0,
        )
        title, text = extract_page_text(resource)
        resolved_url = resource.url
        content_type = resource.content_type
        raw_sha256 = hashlib.sha256(resource.body).hexdigest()
        raw_size_bytes = len(resource.body)
        source_type = "html"

    hits, missing = evidence_coverage(text, list(sample.get("gold_evidence") or []))
    return {
        "sample_id": sample_id,
        "status": "verified-fetched" if not missing else "evidence-mismatch",
        "source_url": url,
        "resolved_url": resolved_url,
        "source_title": title,
        "source_type": source_type,
        "content_type": content_type,
        "fetched_at": fetched_at,
        "raw_sha256": raw_sha256,
        "raw_size_bytes": raw_size_bytes,
        "char_count": len(text.strip()),
        "evidence_total": len(hits) + len(missing),
        "evidence_hits": hits,
        "missing_evidence": missing,
        "text": text,
    }


def existing_snapshot_result(sample: dict, target: Path) -> dict:
    snapshot = verify_source_snapshot(sample, target.read_text(encoding="utf-8"))
    return {
        "sample_id": sample["sample_id"],
        "status": "verified-existing",
        "source_url": sample["source_url"],
        "resolved_url": snapshot.resolved_url,
        "source_title": snapshot.source_title,
        "fetched_at": snapshot.fetched_at,
        "content_sha256": snapshot.content_sha256,
        "raw_sha256": snapshot.raw_sha256,
        "raw_size_bytes": snapshot.raw_size_bytes,
        "char_count": len(snapshot.text),
        "evidence_total": len(sample.get("gold_evidence") or []),
        "evidence_hits": list(sample.get("gold_evidence") or []),
        "missing_evidence": [],
        "path": str(target.relative_to(ROOT)),
    }


async def main_async(
    limit: int | None = None,
    *,
    refresh: bool = False,
    require_all: bool = False,
) -> None:
    cache_dir = ROOT / "data" / "benchmark" / "source_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    samples = load_gold_dataset(ROOT, include_extensions=True)
    validate_gold_dataset(samples)
    if limit:
        samples = samples[:limit]

    manifest: list[dict] = []
    for sample in samples:
        sample_id = sample["sample_id"]
        target = cache_dir / f"{sample_id}.txt"
        if target.exists() and target.stat().st_size > 100 and not refresh:
            try:
                result = existing_snapshot_result(sample, target)
                manifest.append(result)
                print(f"[verified-existing] {sample_id}")
                continue
            except Exception as exc:
                print(f"[invalid-existing] {sample_id}: {exc}; attempting refresh")

        try:
            result = await fetch_sample(sample)
            text = result.pop("text")
            if result["status"] == "evidence-mismatch":
                manifest.append(result)
                print(f"[evidence-mismatch] {sample_id}: {result['missing_evidence']}")
                continue

            snapshot_text = build_source_snapshot(
                origin_source_url=sample["source_url"],
                resolved_url=result["resolved_url"],
                source_title=result["source_title"],
                fetched_at=result["fetched_at"],
                raw_sha256=result["raw_sha256"],
                raw_size_bytes=result["raw_size_bytes"],
                text=text,
            )
            target.write_text(snapshot_text, encoding="utf-8")
            verified = verify_source_snapshot(sample, snapshot_text)
            result["content_sha256"] = verified.content_sha256
            result["path"] = str(target.relative_to(ROOT))
            manifest.append(result)
            print(f"[verified-fetched] {sample_id} ({result['char_count']} chars)")
        except Exception as exc:
            manifest.append(
                {
                    "sample_id": sample_id,
                    "status": "error",
                    "source_url": sample["source_url"],
                    "error": str(exc),
                }
            )
            print(f"[error] {sample_id}: {exc}")

    manifest_path = cache_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    verified = sum(
        1 for item in manifest if item["status"] in {"verified-fetched", "verified-existing"}
    )
    mismatches = sum(1 for item in manifest if item["status"] == "evidence-mismatch")
    errors = sum(1 for item in manifest if item["status"] == "error")
    print(f"done: verified={verified}, evidence-mismatch={mismatches}, errors={errors}")

    if require_all and (verified != len(samples) or mismatches or errors):
        raise SystemExit(
            f"Gold source provenance incomplete: verified={verified}/{len(samples)}, "
            f"evidence-mismatch={mismatches}, errors={errors}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache and verify official sources for the Gold Dataset")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true", help="refetch even when a local cache exists")
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="exit non-zero unless every requested source has a verified snapshot",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.limit, refresh=args.refresh, require_all=args.require_all))


if __name__ == "__main__":
    main()

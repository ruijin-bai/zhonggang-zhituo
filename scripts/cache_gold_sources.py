#!/usr/bin/env python3
import argparse
import asyncio
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.connectors.pdf import PdfConnector  # noqa: E402
from app.gold_dataset import load_gold_dataset, validate_gold_dataset  # noqa: E402
from app.web_fetch import MAX_PAGE_BYTES, extract_page_text, fetch_public_resource  # noqa: E402


def looks_like_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def normalize_evidence(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in re.split(r"\W+", normalized) if part)


def evidence_coverage(text: str, evidence: list[str]) -> tuple[list[str], list[str]]:
    normalized_text = normalize_evidence(text)
    hits: list[str] = []
    missing: list[str] = []
    for item in evidence:
        normalized_item = normalize_evidence(str(item))
        if normalized_item and normalized_item in normalized_text:
            hits.append(str(item))
        else:
            missing.append(str(item))
    return hits, missing


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
        content_sha256 = document.content_sha256
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
        content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        raw_sha256 = hashlib.sha256(resource.body).hexdigest()
        raw_size_bytes = len(resource.body)
        source_type = "html"

    hits, missing = evidence_coverage(text, list(sample.get("gold_evidence") or []))
    return {
        "sample_id": sample_id,
        "status": "cached" if not missing else "evidence-mismatch",
        "source_url": url,
        "resolved_url": resolved_url,
        "source_title": title,
        "source_type": source_type,
        "content_type": content_type,
        "fetched_at": fetched_at,
        "content_sha256": content_sha256,
        "raw_sha256": raw_sha256,
        "raw_size_bytes": raw_size_bytes,
        "char_count": len(text),
        "evidence_total": len(hits) + len(missing),
        "evidence_hits": hits,
        "missing_evidence": missing,
        "text": text,
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
            manifest.append(
                {
                    "sample_id": sample_id,
                    "status": "cached-existing",
                    "source_url": sample["source_url"],
                    "path": str(target.relative_to(ROOT)),
                }
            )
            print(f"[cached-existing] {sample_id}")
            continue

        try:
            result = await fetch_sample(sample)
            text = result.pop("text")
            header = (
                f"SOURCE_URL: {result['resolved_url']}\n"
                f"SOURCE_TITLE: {result['source_title']}\n"
                f"FETCHED_AT: {result['fetched_at']}\n"
                f"CONTENT_SHA256: {result['content_sha256']}\n"
                f"RAW_SHA256: {result['raw_sha256']}\n\n"
            )
            target.write_text(header + text, encoding="utf-8")
            result["path"] = str(target.relative_to(ROOT))
            manifest.append(result)
            if result["status"] == "cached":
                print(f"[ok] {sample_id} ({result['char_count']} chars)")
            else:
                print(f"[evidence-mismatch] {sample_id}: {result['missing_evidence']}")
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

    passed = sum(1 for item in manifest if item["status"] == "cached")
    existing = sum(1 for item in manifest if item["status"] == "cached-existing")
    mismatches = sum(1 for item in manifest if item["status"] == "evidence-mismatch")
    errors = sum(1 for item in manifest if item["status"] == "error")
    print(
        "done: "
        f"verified={passed}, cached-existing={existing}, evidence-mismatch={mismatches}, errors={errors}"
    )

    if require_all and (passed != len(samples) or existing or mismatches or errors):
        raise SystemExit(
            f"Gold source provenance incomplete: verified={passed}/{len(samples)}, "
            f"cached-existing={existing}, evidence-mismatch={mismatches}, errors={errors}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache and verify official sources for the Gold Dataset")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true", help="refetch even when a local cache exists")
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="exit non-zero unless every requested source is fetched and all Gold evidence is found",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.limit, refresh=args.refresh, require_all=args.require_all))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.web_fetch import fetch_public_page  # noqa: E402


def looks_like_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


async def main_async(limit: int | None = None) -> None:
    gold_path = ROOT / "data" / "benchmark" / "gold_dataset.json"
    cache_dir = ROOT / "data" / "benchmark" / "source_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    samples = json.loads(gold_path.read_text(encoding="utf-8"))
    if limit:
        samples = samples[:limit]

    manifest = []
    for sample in samples:
        sample_id = sample["sample_id"]
        url = sample["source_url"]
        target = cache_dir / f"{sample_id}.txt"
        if target.exists() and target.stat().st_size > 100:
            manifest.append({"sample_id": sample_id, "status": "cached", "path": str(target.relative_to(ROOT))})
            print(f"[cached] {sample_id}")
            continue
        if looks_like_pdf(url):
            manifest.append({"sample_id": sample_id, "status": "pdf-manual-required", "url": url})
            print(f"[skip-pdf] {sample_id}")
            continue
        try:
            resolved, title, text = await fetch_public_page(url)
            header = f"SOURCE_URL: {resolved}\nSOURCE_TITLE: {title}\n\n"
            target.write_text(header + text, encoding="utf-8")
            manifest.append({"sample_id": sample_id, "status": "cached", "path": str(target.relative_to(ROOT)), "resolved_url": resolved})
            print(f"[ok] {sample_id} ({len(text)} chars)")
        except Exception as exc:
            manifest.append({"sample_id": sample_id, "status": "error", "url": url, "error": str(exc)})
            print(f"[error] {sample_id}: {exc}")

    (cache_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    cached = sum(1 for item in manifest if item["status"] == "cached")
    pdfs = sum(1 for item in manifest if item["status"] == "pdf-manual-required")
    errors = sum(1 for item in manifest if item["status"] == "error")
    print(f"done: cached={cached}, pdf-manual-required={pdfs}, errors={errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache official HTML source text for Gold Dataset")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main_async(args.limit))


if __name__ == "__main__":
    main()

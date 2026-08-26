#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.ai import AIService  # noqa: E402
from app.connectors import fetch_documents  # noqa: E402

DEFAULT_MANIFEST = ROOT / "data" / "pilot" / "worldbank_sources.json"
DEFAULT_OUTPUT = ROOT / "data" / "pilot" / "latest_run.json"


def _load_manifest(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("pilot manifest must be a non-empty JSON array")
    seen: set[str] = set()
    normalized: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("pilot manifest items must be JSON objects")
        source_id = str(item.get("source_id") or "").strip()
        name = str(item.get("name") or "").strip()
        connector = str(item.get("connector") or "").strip()
        market = str(item.get("market") or "").strip()
        url = str(item.get("url") or "").strip()
        if not all((source_id, name, connector, market, url)):
            raise ValueError("pilot source requires source_id, name, connector, market and url")
        if source_id in seen:
            raise ValueError(f"duplicate pilot source_id: {source_id}")
        seen.add(source_id)
        normalized.append(
            {
                "source_id": source_id,
                "name": name,
                "connector": connector,
                "market": market,
                "url": url,
            }
        )
    return normalized


def _discovery_payload(discovery, *, metadata: dict) -> dict:
    extracted_country = discovery.country
    metadata_country = str(metadata.get("country") or "").strip()
    if extracted_country == "待识别" and metadata_country:
        country = metadata_country
        country_source = "structured_source_metadata"
    else:
        country = extracted_country
        country_source = "extraction"
    return {
        "project_detected": discovery.project_detected,
        "title": discovery.title,
        "country": country,
        "country_source": country_source,
        "sector": discovery.sector,
        "stage": discovery.stage,
        "owner": discovery.owner,
        "estimated_value_usd_m": discovery.estimated_value_usd_m,
        "confidence": discovery.confidence,
        "facts": [
            {
                "field_name": fact.field_name,
                "value": fact.value,
                "confidence": fact.confidence,
                "evidence_quote": fact.evidence_quote,
            }
            for fact in discovery.facts
        ],
        "parties": [
            {
                "role": party.role,
                "name": party.name,
                "country": party.country,
                "confidence": party.confidence,
                "evidence_quote": party.evidence_quote,
            }
            for party in discovery.parties
        ],
    }


async def run_source(
    source: dict,
    *,
    service: AIService,
    use_ai: bool,
    max_documents: int,
) -> dict:
    started = datetime.now(timezone.utc)
    try:
        connector_result = await fetch_documents(source["connector"], source["url"])
        documents = connector_result.documents[:max_documents]
        findings = []
        modes: Counter[str] = Counter()
        for document in documents:
            discovery, mode = await service.discover_project(
                document.text,
                page_title=document.title,
                use_ai=use_ai,
            )
            modes[mode] += 1
            findings.append(
                {
                    "canonical_url": document.canonical_url,
                    "source_title": document.title,
                    "publisher": document.publisher,
                    "published_at": document.published_at.isoformat() if document.published_at else None,
                    "content_sha256": document.content_sha256,
                    "metadata": document.metadata,
                    "extraction_mode": mode,
                    "discovery": _discovery_payload(discovery, metadata=document.metadata),
                }
            )
        return {
            **source,
            "status": "success",
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "source_raw_sha256": connector_result.source_raw_sha256,
            "documents_available": len(connector_result.documents),
            "documents_evaluated": len(documents),
            "projects_detected": sum(
                1 for item in findings if item["discovery"]["project_detected"]
            ),
            "extraction_modes": dict(modes),
            "findings": findings,
        }
    except Exception as exc:
        return {
            **source,
            "status": "error",
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
            "documents_available": 0,
            "documents_evaluated": 0,
            "projects_detected": 0,
            "extraction_modes": {},
            "findings": [],
        }


async def main_async(args) -> int:
    manifest_path = (ROOT / args.manifest).resolve() if not Path(args.manifest).is_absolute() else Path(args.manifest)
    output_path = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    sources = _load_manifest(manifest_path)
    service = AIService()

    results = []
    for source in sources:
        result = await run_source(
            source,
            service=service,
            use_ai=args.ai,
            max_documents=args.max_documents_per_source,
        )
        results.append(result)
        print(
            f"[{result['status']}] {source['market']}: "
            f"docs={result['documents_evaluated']} detected={result['projects_detected']}"
        )
        if result["status"] == "error":
            print(f"  error: {result['error']}")

    successful = [item for item in results if item["status"] == "success"]
    summary = {
        "sources_total": len(results),
        "sources_successful": len(successful),
        "sources_failed": len(results) - len(successful),
        "documents_evaluated": sum(item["documents_evaluated"] for item in results),
        "projects_detected": sum(item["projects_detected"] for item in results),
        "business_claims_publishable": False,
    }
    payload = {
        "pilot_type": "real-public-source-system-run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ai_enabled": bool(args.ai),
        "manifest": str(manifest_path.relative_to(ROOT)),
        "summary": summary,
        "sources": results,
        "note": (
            "This is a real-source system execution record. It does not contain paired human timing or independent business review, "
            "so it must not be presented as efficiency gain, field accuracy, or decision-agreement evidence."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"output: {output_path.relative_to(ROOT)}")
    print("business claims publishable: NO")
    if not successful:
        return 1
    if args.require_all_sources and len(successful) != len(results):
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Zhituo against real public procurement sources")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST.relative_to(ROOT)))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT.relative_to(ROOT)))
    parser.add_argument("--max-documents-per-source", type=int, default=10)
    parser.add_argument("--ai", action="store_true")
    parser.add_argument("--require-all-sources", action="store_true")
    args = parser.parse_args()
    if args.max_documents_per_source < 1 or args.max_documents_per_source > 100:
        parser.error("--max-documents-per-source must be between 1 and 100")
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.candidate_db import CandidateProcessingRecord  # noqa: E402
from app.candidate_pipeline import claim_candidate_processing, process_candidate_document  # noqa: E402
from app.db import (  # noqa: E402
    OpportunityDraftRecord,
    OrganizationRecord,
    SessionLocal,
    set_tenant_context,
)
from app.document_store import build_document_store  # noqa: E402
from app.source_db import (  # noqa: E402
    SourceDocumentRecord,
    SourceFetchRecord,
    SourceScanRunRecord,
    SourceSubscriptionRecord,
)
from app.source_monitoring import (  # noqa: E402
    SourceSubscriptionCreate,
    claim_manual_scan,
    create_subscription,
    scan_subscription,
)

DEFAULT_MANIFEST = ROOT / "data" / "pilot" / "worldbank_sources.json"
DEFAULT_OUTPUT = ROOT / "data" / "pilot" / "latest_persisted_run.json"
PILOT_ORG_CODE = "REAL-SOURCE-PILOT"


def _load_source(path: Path, market: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    matches = [item for item in payload if str(item.get("market") or "").casefold() == market.casefold()]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one pilot source for market {market!r}, found {len(matches)}")
    return matches[0]


def _with_rows(url: str, rows: int) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["rows"] = str(rows)
    query["os"] = "0"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _get_or_create_org(session) -> OrganizationRecord:
    org = session.scalar(select(OrganizationRecord).where(OrganizationRecord.code == PILOT_ORG_CODE))
    if org is not None:
        return org
    org = OrganizationRecord(
        name="Zhituo Real Source Pilot",
        code=PILOT_ORG_CODE,
        is_active=True,
    )
    session.add(org)
    session.commit()
    return org


def _get_or_create_subscription(session, source: dict, url: str) -> SourceSubscriptionRecord:
    existing = session.scalar(
        select(SourceSubscriptionRecord).where(
            SourceSubscriptionRecord.connector == source["connector"],
            SourceSubscriptionRecord.url == url,
        )
    )
    if existing is not None:
        return existing
    return create_subscription(
        session,
        SourceSubscriptionCreate(
            name=f"Persisted pilot · {source['market']}",
            connector=source["connector"],
            url=url,
            interval_seconds=3600,
        ),
    )


async def run(args) -> int:
    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = (ROOT / manifest).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = (ROOT / output).resolve()

    source = _load_source(manifest, args.market)
    source_url = _with_rows(source["url"], args.rows)
    store = build_document_store()
    started_at = datetime.now(timezone.utc)

    session = SessionLocal()
    try:
        org = _get_or_create_org(session)
        set_tenant_context(session, org.id)
        subscription = _get_or_create_subscription(session, source, source_url)

        before = {
            "fetches": _count(session, SourceFetchRecord),
            "documents": _count(session, SourceDocumentRecord),
            "candidate_processing": _count(session, CandidateProcessingRecord),
            "drafts": _count(session, OpportunityDraftRecord),
        }

        _, scan_token = claim_manual_scan(session, subscription.id)
        scan = await scan_subscription(
            session,
            subscription.id,
            manual=True,
            lease_token=scan_token,
            store=store,
        )
        if scan.outcome == "failed":
            raise RuntimeError(f"source subscription scan failed: {scan.error}")
        if scan.documents_seen < 1:
            raise RuntimeError("real source scan returned no documents")

        claims = claim_candidate_processing(session, limit=max(args.rows * 2, 10))
        processing_results = []
        for processing_id, lease_token in claims:
            result = await process_candidate_document(
                session,
                processing_id,
                lease_token=lease_token,
                store=store,
            )
            processing_results.append(result)

        bad = [item for item in processing_results if item.status in {"retry", "failed", "stale_claim"}]
        if bad:
            raise RuntimeError(
                "candidate processing did not complete cleanly: "
                + ", ".join(f"{item.processing_id}:{item.status}:{item.error}" for item in bad)
            )

        created_draft_ids = [item.draft_id for item in processing_results if item.status == "candidate_created" and item.draft_id]
        if args.require_new_draft and not created_draft_ids:
            raise RuntimeError("persisted real-source pilot created no Opportunity Draft")

        created_drafts = [session.get(OpportunityDraftRecord, draft_id) for draft_id in created_draft_ids]
        draft_snapshots = [
            {
                "id": draft.id,
                "title": draft.discovery.get("title"),
                "country": draft.discovery.get("country"),
                "sector": draft.discovery.get("sector"),
                "source_url": draft.source_url,
                "status": draft.status,
            }
            for draft in created_drafts
            if draft is not None
        ]
        if args.require_market_country and any(
            item["country"] != source["market"] for item in draft_snapshots
        ):
            raise RuntimeError(
                f"draft country did not preserve authoritative source market {source['market']!r}"
            )

        after = {
            "fetches": _count(session, SourceFetchRecord),
            "documents": _count(session, SourceDocumentRecord),
            "candidate_processing": _count(session, CandidateProcessingRecord),
            "scan_runs": _count(session, SourceScanRunRecord),
            "drafts": _count(session, OpportunityDraftRecord),
        }
        status_counts = Counter(item.status for item in processing_results)
        payload = {
            "pilot_type": "persisted-real-public-source-e2e",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "started_at": started_at.isoformat(),
            "market": source["market"],
            "connector": source["connector"],
            "source_url": source_url,
            "organization_code": PILOT_ORG_CODE,
            "scan": scan.model_dump(mode="json"),
            "before": before,
            "after": after,
            "processing_claims": len(claims),
            "processing_statuses": dict(status_counts),
            "created_drafts": draft_snapshots,
            "business_claims_publishable": False,
            "note": (
                "This run proves the real external source can traverse Source Subscription, PostgreSQL archive, "
                "durable Candidate Processing and Opportunity Draft persistence. It does not prove human time savings, "
                "business accuracy or decision agreement."
            ),
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print(
            f"market={source['market']} scan={scan.outcome} docs={scan.documents_seen} "
            f"created={scan.documents_created} claims={len(claims)} drafts={len(created_draft_ids)}"
        )
        print(f"processing={dict(status_counts)}")
        print(f"tables(before)={before}")
        print(f"tables(after)={after}")
        for draft in draft_snapshots:
            print(f"draft={draft['id']} country={draft['country']} sector={draft['sector']} title={draft['title']}")
        print(f"output={output.relative_to(ROOT)}")
        print("business claims publishable: NO")
        return 0
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real World Bank source through Zhituo's persisted production path")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST.relative_to(ROOT)))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT.relative_to(ROOT)))
    parser.add_argument("--market", default="Zambia")
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--require-new-draft", action="store_true")
    parser.add_argument("--require-market-country", action="store_true")
    args = parser.parse_args()
    if args.rows < 1 or args.rows > 25:
        parser.error("--rows must be between 1 and 25")
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

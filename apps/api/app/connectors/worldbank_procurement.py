from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from urllib.parse import quote_plus, urlparse

from ..web_fetch import MAX_PAGE_BYTES, fetch_public_resource
from .base import ConnectorFetchOutcome, ConnectorResult, build_document

WORLD_BANK_PROCUREMENT_HOST = "search.worldbank.org"
WORLD_BANK_PROCUREMENT_PATH = "/api/v2/procnotices"
WORLD_BANK_PUBLISHER = "World Bank Group"


def _validate_worldbank_procurement_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("World Bank procurement source must use HTTPS")
    if parsed.hostname != WORLD_BANK_PROCUREMENT_HOST:
        raise ValueError("World Bank procurement connector only accepts search.worldbank.org")
    if parsed.path.rstrip("/") != WORLD_BANK_PROCUREMENT_PATH:
        raise ValueError("World Bank procurement connector only accepts /api/v2/procnotices")
    return url


def _first(record: dict, *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%b-%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _notice_records(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        raise ValueError("World Bank procurement API returned a non-object JSON payload")

    container = payload.get("procnotices")
    if container is None:
        container = payload.get("documents")
    if container is None:
        container = payload.get("results")
    if container is None:
        raise ValueError("World Bank procurement API payload has no notice collection")

    if isinstance(container, list):
        records = [item for item in container if isinstance(item, dict)]
    elif isinstance(container, dict):
        if isinstance(container.get("docs"), list):
            records = [item for item in container["docs"] if isinstance(item, dict)]
        else:
            records = [item for item in container.values() if isinstance(item, dict)]
    else:
        raise ValueError("World Bank procurement notice collection has an unsupported shape")

    if not records:
        raise ValueError("World Bank procurement API returned zero notice records")
    return records


def _notice_text(record: dict) -> tuple[str, str, str, datetime | None, dict]:
    notice_id = _first(record, "id", "notice_id", "noticeid")
    title = _first(
        record,
        "bid_description",
        "description",
        "notice_text",
        "notice_title",
        "project_name",
    )
    if not notice_id:
        raise ValueError("World Bank procurement notice is missing id")
    if not title:
        title = f"World Bank procurement notice {notice_id}"

    fields = [
        ("Notice ID", notice_id),
        ("Notice Type", _first(record, "notice_type", "notice_type_exact")),
        ("Published Date", _first(record, "publication_date", "published_date", "notice_date")),
        ("Submission Deadline", _first(record, "submission_deadline_date", "submission_date", "deadline_date")),
        ("Country", _first(record, "project_ctry_name", "country_name", "country")),
        ("Project ID", _first(record, "project_id", "projectid")),
        ("Project", _first(record, "project_name", "project_title")),
        ("Bid Reference", _first(record, "bid_reference", "bid_ref", "reference_no")),
        ("Description", title),
        ("Procurement Category", _first(record, "procurement_category", "category")),
        ("Procurement Method", _first(record, "procurement_method", "procurement_method_name")),
        ("Contact Organization", _first(record, "contact_organization", "organization_name", "borrower")),
        ("Contact Name", _first(record, "contact_name")),
        ("Contact Email", _first(record, "contact_email", "email")),
    ]
    text = "\n".join(f"{label}: {value}" for label, value in fields if value)
    published_at = _parse_datetime(_first(record, "publication_date", "published_date", "notice_date"))
    canonical_url = (
        "https://search.worldbank.org/api/v2/procnotices"
        f"?format=json&id={quote_plus(notice_id)}"
    )
    metadata = {
        "notice_id": notice_id,
        "notice_type": _first(record, "notice_type", "notice_type_exact"),
        "country": _first(record, "project_ctry_name", "country_name", "country"),
        "project_id": _first(record, "project_id", "projectid"),
        "project_name": _first(record, "project_name", "project_title"),
        "submission_deadline_date": _first(
            record,
            "submission_deadline_date",
            "submission_date",
            "deadline_date",
        ),
        "contact_address": _first(record, "contact_address", "address"),
    }
    return canonical_url, title, text, published_at, metadata


class WorldBankProcurementConnector:
    kind = "worldbank_procurement"

    async def fetch(self, url: str) -> ConnectorResult:
        outcome = await self.fetch_conditional(url)
        if outcome.result is None:
            raise RuntimeError("unconditional World Bank procurement fetch returned not-modified")
        return outcome.result

    async def fetch_conditional(
        self,
        url: str,
        *,
        if_none_match: str | None = None,
        if_modified_since: str | None = None,
    ) -> ConnectorFetchOutcome:
        source_url = _validate_worldbank_procurement_url(url.strip())
        resource = await fetch_public_resource(
            source_url,
            max_bytes=MAX_PAGE_BYTES,
            accept="application/json,text/json;q=0.9,*/*;q=0.1",
            if_none_match=if_none_match,
            if_modified_since=if_modified_since,
        )
        if resource.not_modified:
            return ConnectorFetchOutcome(
                connector=self.kind,
                source_url=resource.url,
                not_modified=True,
                etag=resource.etag,
                last_modified=resource.last_modified,
            )

        try:
            payload = json.loads(resource.body.decode(resource.encoding or "utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("World Bank procurement source did not return valid JSON") from exc

        documents = []
        raw_objects: dict[str, bytes] = {}
        for record in _notice_records(payload):
            canonical_url, title, text, published_at, metadata = _notice_text(record)
            raw = json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            document = build_document(
                connector=self.kind,
                canonical_url=canonical_url,
                title=title,
                text=text,
                content_type="application/json",
                raw=raw,
                publisher=WORLD_BANK_PUBLISHER,
                published_at=published_at,
                metadata=metadata,
            )
            documents.append(document)
            raw_objects[document.raw_sha256] = raw

        source_raw_sha256 = sha256(resource.body).hexdigest()
        raw_objects[source_raw_sha256] = resource.body
        result = ConnectorResult(
            connector=self.kind,
            source_url=resource.url,
            source_content_type=resource.content_type or "application/json",
            source_raw_sha256=source_raw_sha256,
            source_raw_size_bytes=len(resource.body),
            documents=documents,
            raw_objects=raw_objects,
        )
        return ConnectorFetchOutcome(
            connector=self.kind,
            source_url=resource.url,
            etag=resource.etag,
            last_modified=resource.last_modified,
            result=result,
        )

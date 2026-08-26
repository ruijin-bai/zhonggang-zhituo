from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from .gold_dataset import normalize_source_url

REQUIRED_HEADERS = (
    "ORIGIN_SOURCE_URL",
    "RESOLVED_URL",
    "SOURCE_TITLE",
    "FETCHED_AT",
    "CONTENT_SHA256",
    "RAW_SHA256",
    "RAW_SIZE_BYTES",
)


@dataclass(frozen=True)
class VerifiedSourceSnapshot:
    origin_source_url: str
    resolved_url: str
    source_title: str
    fetched_at: str
    content_sha256: str
    raw_sha256: str
    raw_size_bytes: int
    text: str


def normalize_evidence(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in re.split(r"\W+", normalized) if part)


def evidence_coverage(text: str, evidence: list[str]) -> tuple[list[str], list[str]]:
    normalized_text = normalize_evidence(text)
    hits: list[str] = []
    missing: list[str] = []
    for item in evidence:
        candidate = str(item)
        normalized_item = normalize_evidence(candidate)
        if normalized_item and normalized_item in normalized_text:
            hits.append(candidate)
        else:
            missing.append(candidate)
    return hits, missing


def build_source_snapshot(
    *,
    origin_source_url: str,
    resolved_url: str,
    source_title: str,
    fetched_at: str,
    raw_sha256: str,
    raw_size_bytes: int,
    text: str,
) -> str:
    body = text.strip()
    content_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    header = (
        f"ORIGIN_SOURCE_URL: {origin_source_url}\n"
        f"RESOLVED_URL: {resolved_url}\n"
        f"SOURCE_TITLE: {source_title}\n"
        f"FETCHED_AT: {fetched_at}\n"
        f"CONTENT_SHA256: {content_sha256}\n"
        f"RAW_SHA256: {raw_sha256}\n"
        f"RAW_SIZE_BYTES: {raw_size_bytes}\n\n"
    )
    return header + body


def parse_source_snapshot(raw: str) -> VerifiedSourceSnapshot:
    header_text, separator, text = raw.partition("\n\n")
    if not separator:
        raise ValueError("snapshot metadata header is missing")

    headers: dict[str, str] = {}
    for line in header_text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            headers[key.strip()] = value.strip()

    missing_headers = [key for key in REQUIRED_HEADERS if not headers.get(key)]
    if missing_headers:
        raise ValueError(f"snapshot metadata missing: {', '.join(missing_headers)}")

    body = text.strip()
    if len(body) < 40:
        raise ValueError("snapshot body is too short")

    actual_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if actual_sha256 != headers["CONTENT_SHA256"]:
        raise ValueError("snapshot content SHA-256 mismatch")

    try:
        raw_size_bytes = int(headers["RAW_SIZE_BYTES"])
    except ValueError as exc:
        raise ValueError("snapshot RAW_SIZE_BYTES must be an integer") from exc
    if raw_size_bytes <= 0:
        raise ValueError("snapshot RAW_SIZE_BYTES must be positive")

    return VerifiedSourceSnapshot(
        origin_source_url=headers["ORIGIN_SOURCE_URL"],
        resolved_url=headers["RESOLVED_URL"],
        source_title=headers["SOURCE_TITLE"],
        fetched_at=headers["FETCHED_AT"],
        content_sha256=headers["CONTENT_SHA256"],
        raw_sha256=headers["RAW_SHA256"],
        raw_size_bytes=raw_size_bytes,
        text=body,
    )


def verify_source_snapshot(sample: dict, raw: str) -> VerifiedSourceSnapshot:
    snapshot = parse_source_snapshot(raw)
    expected_url = str(sample.get("source_url") or "").strip()
    if not expected_url:
        raise ValueError("Gold sample source_url is missing")
    if normalize_source_url(snapshot.origin_source_url) != normalize_source_url(expected_url):
        raise ValueError("snapshot origin URL does not match Gold source_url")

    _, missing = evidence_coverage(snapshot.text, list(sample.get("gold_evidence") or []))
    if missing:
        raise ValueError(f"snapshot is missing Gold evidence: {missing}")
    return snapshot

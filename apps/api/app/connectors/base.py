from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol

from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    """Normalized document emitted by every external source connector."""

    connector: str
    canonical_url: str
    title: str
    text: str
    content_type: str
    content_sha256: str
    raw_sha256: str
    raw_size_bytes: int
    publisher: str | None = None
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorResult(BaseModel):
    """Serializable connector metadata plus transient raw bytes for archival."""

    connector: str
    source_url: str
    source_content_type: str
    source_raw_sha256: str
    source_raw_size_bytes: int
    documents: list[SourceDocument]
    raw_objects: dict[str, bytes] = Field(default_factory=dict, exclude=True, repr=False)


class SourceConnector(Protocol):
    kind: str

    async def fetch(self, url: str) -> ConnectorResult: ...


def build_document(
    *,
    connector: str,
    canonical_url: str,
    title: str,
    text: str,
    content_type: str,
    raw: bytes,
    publisher: str | None = None,
    published_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> SourceDocument:
    normalized_text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return SourceDocument(
        connector=connector,
        canonical_url=canonical_url,
        title=title.strip() or canonical_url,
        text=normalized_text,
        content_type=content_type,
        content_sha256=sha256(normalized_text.encode("utf-8")).hexdigest(),
        raw_sha256=sha256(raw).hexdigest(),
        raw_size_bytes=len(raw),
        publisher=publisher,
        published_at=published_at,
        metadata=metadata or {},
    )

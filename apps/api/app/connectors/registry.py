from __future__ import annotations

from .base import ConnectorResult, SourceConnector
from .html import HtmlConnector
from .pdf import PdfConnector
from .rss import RssConnector

_CONNECTORS: dict[str, SourceConnector] = {
    "html": HtmlConnector(),
    "rss": RssConnector(),
    "pdf": PdfConnector(),
}


def connector_kinds() -> tuple[str, ...]:
    return tuple(sorted(_CONNECTORS))


def get_connector(kind: str) -> SourceConnector:
    normalized = kind.strip().lower()
    try:
        return _CONNECTORS[normalized]
    except KeyError as exc:
        available = ", ".join(connector_kinds())
        raise ValueError(f"未知 Source Connector: {kind}; 可用类型: {available}") from exc


async def fetch_documents(kind: str, url: str) -> ConnectorResult:
    return await get_connector(kind).fetch(url)

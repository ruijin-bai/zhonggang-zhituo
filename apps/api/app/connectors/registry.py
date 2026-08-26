from __future__ import annotations

from .base import ConnectorFetchOutcome, ConnectorResult, SourceConnector
from .html import HtmlConnector
from .pdf import PdfConnector
from .rss import RssConnector
from .worldbank_procurement import WorldBankProcurementConnector

_CONNECTORS: dict[str, SourceConnector] = {
    "html": HtmlConnector(),
    "rss": RssConnector(),
    "pdf": PdfConnector(),
    "worldbank_procurement": WorldBankProcurementConnector(),
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


async def fetch_documents_conditional(
    kind: str,
    url: str,
    *,
    if_none_match: str | None = None,
    if_modified_since: str | None = None,
) -> ConnectorFetchOutcome:
    return await get_connector(kind).fetch_conditional(
        url,
        if_none_match=if_none_match,
        if_modified_since=if_modified_since,
    )

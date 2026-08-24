from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from xml.etree import ElementTree

from .base import ConnectorResult, SourceDocument, build_document
from ..web_fetch import PublicResource, fetch_public_resource, html_to_text

MAX_FEED_BYTES = 5_000_000
MAX_FEED_ENTRIES = 100
RSS_CONTENT_TYPES = {
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ElementTree.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(element):
        if _local_name(child.tag) in wanted:
            return "".join(child.itertext()).strip()
    return ""


def _feed_container(root: ElementTree.Element) -> ElementTree.Element:
    """Return the element that owns feed metadata and entries for RSS or Atom."""

    if _local_name(root.tag) == "rss":
        for child in list(root):
            if _local_name(child.tag) == "channel":
                return child
        raise ValueError("RSS 订阅源缺少 channel 节点")
    return root


def _entry_link(element: ElementTree.Element) -> str:
    fallback = ""
    for child in list(element):
        if _local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        rel = (child.attrib.get("rel") or "alternate").lower()
        if href and rel in {"alternate", ""}:
            return href
        if href and not fallback:
            fallback = href
        text = "".join(child.itertext()).strip()
        if text and not fallback:
            fallback = text
    return fallback


def _parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed is not None:
            return parsed
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _markup_text(value: str) -> str:
    if not value:
        return ""
    _, text = html_to_text(value)
    return text or " ".join(value.split())


def parse_feed_resource(resource: PublicResource) -> list[SourceDocument]:
    if resource.content_type and resource.content_type not in RSS_CONTENT_TYPES:
        prefix = resource.body.lstrip()[:200].lower()
        if not (prefix.startswith(b"<?xml") or b"<rss" in prefix or b"<feed" in prefix):
            raise ValueError("当前 URL 不是 RSS/Atom/XML 订阅源")

    try:
        root = ElementTree.fromstring(resource.body)
    except ElementTree.ParseError as exc:
        raise ValueError("RSS/Atom XML 无法解析") from exc

    feed = _feed_container(root)
    feed_title = _child_text(feed, "title")
    publisher = feed_title or None
    entries = [
        element
        for element in feed.iter()
        if _local_name(element.tag) in {"item", "entry"}
    ]
    if not entries:
        raise ValueError("RSS/Atom 订阅源中没有可处理条目")

    documents: list[SourceDocument] = []
    for index, entry in enumerate(entries[:MAX_FEED_ENTRIES]):
        title = _child_text(entry, "title") or f"Feed entry {index + 1}"
        link = _entry_link(entry) or f"{resource.url}#entry-{index + 1}"
        summary = _child_text(entry, "content", "encoded", "description", "summary")
        text = _markup_text(summary)
        if len(text) < 20:
            text = title
        published = _parse_datetime(
            _child_text(entry, "published", "updated", "pubdate", "date")
        )
        documents.append(
            build_document(
                connector="rss",
                canonical_url=link,
                title=title,
                text=text,
                content_type=resource.content_type or "application/xml",
                raw=resource.body,
                publisher=publisher,
                published_at=published,
                metadata={
                    "feed_url": resource.url,
                    "feed_title": feed_title,
                    "entry_index": index,
                },
            )
        )
    return documents


class RssConnector:
    kind = "rss"

    async def fetch(self, url: str) -> ConnectorResult:
        resource = await fetch_public_resource(
            url,
            max_bytes=MAX_FEED_BYTES,
            accept=(
                "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,"
                "*/*;q=0.1"
            ),
        )
        documents = parse_feed_resource(resource)
        raw_digest = sha256(resource.body).hexdigest()
        return ConnectorResult(
            connector=self.kind,
            source_url=resource.url,
            source_content_type=resource.content_type or "application/xml",
            source_raw_sha256=raw_digest,
            source_raw_size_bytes=len(resource.body),
            documents=documents,
            raw_objects={raw_digest: resource.body},
        )

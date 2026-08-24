import asyncio
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.connectors.base import build_document
from app.connectors.html import HtmlConnector
from app.connectors.pdf import parse_pdf_resource
from app.connectors.registry import connector_kinds, get_connector
from app.connectors.rss import parse_feed_resource
from app.web_fetch import PublicResource


def test_build_document_hashes_are_stable():
    first = build_document(
        connector="html",
        canonical_url="https://example.com/a",
        title="Project A",
        text=" first line \n\n second line ",
        content_type="text/html",
        raw=b"raw-document",
    )
    second = build_document(
        connector="html",
        canonical_url="https://example.com/a",
        title="Project A",
        text="first line\nsecond line",
        content_type="text/html",
        raw=b"raw-document",
    )
    assert first.content_sha256 == second.content_sha256
    assert first.raw_sha256 == second.raw_sha256
    assert first.text == "first line\nsecond line"


def test_html_connector_emits_normalized_document(monkeypatch):
    resource = PublicResource(
        url="https://example.com/project",
        content_type="text/html",
        body=b"<html><head><title>Port Project</title></head><body><p>" + b"A" * 60 + b"</p></body></html>",
        encoding="utf-8",
    )

    async def fake_fetch(*args, **kwargs):
        return resource

    monkeypatch.setattr("app.connectors.html.fetch_public_resource", fake_fetch)
    result = asyncio.run(HtmlConnector().fetch(resource.url))
    assert result.connector == "html"
    assert len(result.documents) == 1
    assert result.documents[0].title == "Port Project"
    assert result.documents[0].raw_size_bytes == len(resource.body)


def test_rss_connector_parses_rss_items():
    raw = b"""<?xml version='1.0' encoding='UTF-8'?>
    <rss version='2.0'>
      <channel>
        <title>Infrastructure Procurement</title>
        <item>
          <title>New Port Tender</title>
          <link>https://example.com/tenders/1</link>
          <pubDate>Mon, 24 Aug 2026 10:00:00 GMT</pubDate>
          <description><![CDATA[<p>International tender for a new port terminal and access road.</p>]]></description>
        </item>
        <item>
          <title>Bridge Procurement</title>
          <link>https://example.com/tenders/2</link>
          <description>Bridge engineering procurement notice.</description>
        </item>
      </channel>
    </rss>"""
    resource = PublicResource(
        url="https://example.com/feed.xml",
        content_type="application/rss+xml",
        body=raw,
        encoding="utf-8",
    )
    documents = parse_feed_resource(resource)
    assert len(documents) == 2
    assert documents[0].title == "New Port Tender"
    assert documents[0].publisher == "Infrastructure Procurement"
    assert documents[0].canonical_url == "https://example.com/tenders/1"
    assert documents[0].published_at is not None


def test_atom_connector_parses_feed_metadata_and_href_link():
    raw = b"""<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns='http://www.w3.org/2005/Atom'>
      <title>Development Bank Projects</title>
      <entry>
        <title>Regional Highway Program</title>
        <link rel='alternate' href='https://example.com/projects/highway'/>
        <updated>2026-08-24T11:30:00Z</updated>
        <summary>Financing approved for a regional highway construction program.</summary>
      </entry>
    </feed>"""
    resource = PublicResource(
        url="https://example.com/atom.xml",
        content_type="application/atom+xml",
        body=raw,
        encoding="utf-8",
    )
    documents = parse_feed_resource(resource)
    assert len(documents) == 1
    assert documents[0].publisher == "Development Bank Projects"
    assert documents[0].title == "Regional Highway Program"
    assert documents[0].canonical_url == "https://example.com/projects/highway"
    assert documents[0].published_at is not None


def test_pdf_connector_rejects_image_only_or_empty_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    output = BytesIO()
    writer.write(output)
    resource = PublicResource(
        url="https://example.com/tender.pdf",
        content_type="application/pdf",
        body=output.getvalue(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="OCR"):
        parse_pdf_resource(resource)


def test_connector_registry_is_explicit():
    assert connector_kinds() == ("html", "pdf", "rss")
    assert get_connector("PDF").kind == "pdf"
    with pytest.raises(ValueError, match="未知 Source Connector"):
        get_connector("crawler")

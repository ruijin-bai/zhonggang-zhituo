from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.connectors import connector_kinds, get_connector
from app.connectors.base import build_document
from app.connectors.html import HtmlConnector
from app.connectors.pdf import PdfConnector, parse_pdf_resource
from app.connectors.rss import RssConnector
from app.web_fetch import PublicResource


def test_build_document_hashes_raw_and_normalized_content():
    document = build_document(
        connector="html",
        canonical_url="https://example.com/project",
        title="Project",
        text="Alpha project notice",
        content_type="text/html",
        raw=b"<html>Alpha project notice</html>",
        publisher="Example",
    )
    assert document.connector == "html"
    assert document.raw_sha256
    assert document.content_sha256
    assert document.raw_sha256 != document.content_sha256
    assert document.raw_size_bytes == len(b"<html>Alpha project notice</html>")


def test_html_connector_maps_one_page_to_one_document(monkeypatch):
    resource = PublicResource(
        url="https://example.com/project",
        content_type="text/html",
        body=b"<html><head><title>Project</title></head><body>Alpha project notice</body></html>",
        encoding="utf-8",
    )

    async def fake_fetch(url, **kwargs):
        return resource

    monkeypatch.setattr("app.connectors.html.fetch_public_resource", fake_fetch)
    result = __import__("asyncio").run(HtmlConnector().fetch(resource.url))
    assert result.connector == "html"
    assert len(result.documents) == 1
    assert result.documents[0].title == "Project"
    assert result.documents[0].text == "Alpha project notice"
    assert result.source_raw_sha256 in result.raw_objects


def test_pdf_connector_maps_one_pdf_to_one_document(monkeypatch):
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

    async def fake_fetch(url, **kwargs):
        return resource

    monkeypatch.setattr("app.connectors.pdf.fetch_public_resource", fake_fetch)
    with pytest.raises(ValueError, match="OCR"):
        __import__("asyncio").run(PdfConnector().fetch(resource.url))


def test_rss_connector_maps_entries_to_documents(monkeypatch):
    resource = PublicResource(
        url="https://example.com/feed.xml",
        content_type="application/rss+xml",
        body=b"""<?xml version='1.0' encoding='UTF-8'?>
<rss version='2.0'>
  <channel>
    <title>Example feed</title>
    <item>
      <title>Road Project</title>
      <link>https://example.com/road</link>
      <description>Invitation for bids for a road project.</description>
    </item>
  </channel>
</rss>""",
        encoding="utf-8",
    )

    async def fake_fetch(url, **kwargs):
        return resource

    monkeypatch.setattr("app.connectors.rss.fetch_public_resource", fake_fetch)
    result = __import__("asyncio").run(RssConnector().fetch(resource.url))
    assert len(result.documents) == 1
    assert result.documents[0].canonical_url == "https://example.com/road"
    assert "Invitation for bids" in result.documents[0].text


def test_pdf_parser_rejects_blank_scanned_document_without_ocr():
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
    assert connector_kinds() == ("html", "pdf", "rss", "worldbank_procurement")
    assert get_connector("PDF").kind == "pdf"
    with pytest.raises(ValueError, match="未知 Source Connector"):
        get_connector("crawler")

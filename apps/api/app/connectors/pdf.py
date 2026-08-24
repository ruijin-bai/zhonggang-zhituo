from __future__ import annotations

from io import BytesIO
from urllib.parse import unquote, urlparse

from pypdf import PdfReader

from .base import ConnectorResult, SourceDocument, build_document
from ..web_fetch import PublicResource, fetch_public_resource

MAX_PDF_BYTES = 25_000_000
MAX_PDF_PAGES = 300
MAX_PDF_TEXT_CHARS = 500_000


def parse_pdf_resource(resource: PublicResource) -> SourceDocument:
    if resource.content_type and resource.content_type != "application/pdf":
        if not resource.body.startswith(b"%PDF"):
            raise ValueError("当前 URL 不是 PDF 文档")
    elif not resource.body.startswith(b"%PDF"):
        raise ValueError("PDF 文件签名无效")

    try:
        reader = PdfReader(BytesIO(resource.body), strict=False)
    except Exception as exc:  # pypdf exposes several parser-specific exceptions
        raise ValueError("PDF 文档无法解析") from exc

    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise ValueError("PDF 已加密，当前连接器无法读取") from exc
        if not unlocked:
            raise ValueError("PDF 已加密，当前连接器无法读取")

    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise ValueError(f"PDF 页数超过 {MAX_PDF_PAGES} 页安全限制")

    parts: list[str] = []
    total_chars = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = (page.extract_text() or "").strip()
        except Exception as exc:
            raise ValueError(f"PDF 第 {page_number} 页文本提取失败") from exc
        if not page_text:
            continue
        remaining = MAX_PDF_TEXT_CHARS - total_chars
        if remaining <= 0:
            break
        clipped = page_text[:remaining]
        parts.append(clipped)
        total_chars += len(clipped)

    text = "\n\n".join(parts).strip()
    if len(text) < 40:
        raise ValueError("PDF 未提取到足够可用的文本；扫描件需后续 OCR 管线处理")

    metadata = reader.metadata
    title = ""
    if metadata is not None:
        title = (getattr(metadata, "title", None) or "").strip()
    if not title:
        path_name = unquote(urlparse(resource.url).path.rsplit("/", 1)[-1])
        title = path_name or "PDF document"

    return build_document(
        connector="pdf",
        canonical_url=resource.url,
        title=title,
        text=text,
        content_type="application/pdf",
        raw=resource.body,
        metadata={
            "page_count": page_count,
            "text_truncated": total_chars >= MAX_PDF_TEXT_CHARS,
        },
    )


class PdfConnector:
    kind = "pdf"

    async def fetch(self, url: str) -> ConnectorResult:
        resource = await fetch_public_resource(
            url,
            max_bytes=MAX_PDF_BYTES,
            accept="application/pdf,*/*;q=0.1",
            timeout_seconds=30.0,
        )
        document = parse_pdf_resource(resource)
        return ConnectorResult(
            connector=self.kind,
            source_url=resource.url,
            source_content_type="application/pdf",
            source_raw_sha256=document.raw_sha256,
            source_raw_size_bytes=len(resource.body),
            documents=[document],
            raw_objects={document.raw_sha256: resource.body},
        )

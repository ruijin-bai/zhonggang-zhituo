from urllib.parse import urlparse

from .base import ConnectorFetchOutcome, ConnectorResult, build_document
from ..web_fetch import MAX_PAGE_BYTES, extract_page_text, fetch_public_resource


class HtmlConnector:
    kind = "html"

    async def fetch(self, url: str) -> ConnectorResult:
        outcome = await self.fetch_conditional(url)
        if outcome.result is None:
            raise RuntimeError("unconditional HTML fetch unexpectedly returned not-modified")
        return outcome.result

    async def fetch_conditional(
        self,
        url: str,
        *,
        if_none_match: str | None = None,
        if_modified_since: str | None = None,
    ) -> ConnectorFetchOutcome:
        resource = await fetch_public_resource(
            url,
            max_bytes=MAX_PAGE_BYTES,
            accept="text/html,text/plain;q=0.9,application/xhtml+xml;q=0.8,*/*;q=0.1",
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

        title, text = extract_page_text(resource)
        fallback_title = urlparse(resource.url).path.rsplit("/", 1)[-1] or resource.url
        document = build_document(
            connector=self.kind,
            canonical_url=resource.url,
            title=title or fallback_title,
            text=text,
            content_type=resource.content_type or "text/html",
            raw=resource.body,
        )
        result = ConnectorResult(
            connector=self.kind,
            source_url=resource.url,
            source_content_type=resource.content_type or "text/html",
            source_raw_sha256=document.raw_sha256,
            source_raw_size_bytes=len(resource.body),
            documents=[document],
            raw_objects={document.raw_sha256: resource.body},
        )
        return ConnectorFetchOutcome(
            connector=self.kind,
            source_url=resource.url,
            etag=resource.etag,
            last_modified=resource.last_modified,
            result=result,
        )

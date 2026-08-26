import asyncio

from app.connectors.html import HtmlConnector
from app.web_fetch import PUBLIC_FETCH_USER_AGENT, PublicResource, fetch_public_resource


def test_public_fetch_sends_cache_validators_and_handles_304(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        status_code = 304
        headers = {
            "etag": '"etag-v2"',
            "last-modified": "Mon, 24 Aug 2026 12:00:00 GMT",
        }
        encoding = "utf-8"

        def raise_for_status(self):
            raise AssertionError("304 must return before raise_for_status")

        async def aiter_bytes(self):
            if False:
                yield b""

    class StreamContext:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeClient:
        def __init__(self, *, headers, **kwargs):
            captured["headers"] = dict(headers)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            captured["method"] = method
            captured["url"] = url
            return StreamContext()

    monkeypatch.setattr("app.web_fetch.httpx.AsyncClient", FakeClient)

    resource = asyncio.run(
        fetch_public_resource(
            "https://8.8.8.8/feed",
            max_bytes=1024,
            if_none_match='"etag-v1"',
            if_modified_since="Sun, 23 Aug 2026 12:00:00 GMT",
        )
    )

    assert captured["method"] == "GET"
    assert captured["headers"]["User-Agent"] == PUBLIC_FETCH_USER_AGENT
    assert captured["headers"]["Accept-Language"] == "en-US,en;q=0.9"
    assert captured["headers"]["Cache-Control"] == "no-cache"
    assert captured["headers"]["If-None-Match"] == '"etag-v1"'
    assert captured["headers"]["If-Modified-Since"] == "Sun, 23 Aug 2026 12:00:00 GMT"
    assert resource.not_modified is True
    assert resource.body == b""
    assert resource.etag == '"etag-v2"'
    assert resource.last_modified == "Mon, 24 Aug 2026 12:00:00 GMT"


def test_html_connector_preserves_304_metadata(monkeypatch):
    resource = PublicResource(
        url="https://8.8.8.8/project",
        content_type="",
        body=b"",
        encoding="utf-8",
        status_code=304,
        etag='"project-v4"',
        last_modified="Mon, 24 Aug 2026 13:00:00 GMT",
    )
    captured: dict = {}

    async def fake_fetch(url, **kwargs):
        captured.update(kwargs)
        return resource

    monkeypatch.setattr("app.connectors.html.fetch_public_resource", fake_fetch)
    outcome = asyncio.run(
        HtmlConnector().fetch_conditional(
            resource.url,
            if_none_match='"project-v3"',
            if_modified_since="Sun, 23 Aug 2026 13:00:00 GMT",
        )
    )

    assert captured["if_none_match"] == '"project-v3"'
    assert captured["if_modified_since"] == "Sun, 23 Aug 2026 13:00:00 GMT"
    assert outcome.not_modified is True
    assert outcome.result is None
    assert outcome.etag == '"project-v4"'
    assert outcome.last_modified == "Mon, 24 Aug 2026 13:00:00 GMT"

import asyncio
import json

import pytest

from app.connectors import connector_kinds
from app.connectors.worldbank_procurement import WorldBankProcurementConnector
from app.web_fetch import PublicResource


SOURCE_URL = (
    "https://search.worldbank.org/api/v2/procnotices"
    "?format=json&rows=25&os=0&project_ctry_name=Nigeria"
)


def _payload() -> bytes:
    return json.dumps(
        {
            "total": 2,
            "procnotices": {
                "OP00470001": {
                    "id": "OP00470001",
                    "notice_type": "Invitation for Bids",
                    "publication_date": "22-Jul-2026",
                    "submission_deadline_date": "2026-09-01",
                    "project_ctry_name": "Nigeria",
                    "project_id": "P172891",
                    "project_name": "Nigeria Distribution Sector Recovery Program",
                    "bid_reference": "NG-NERC-001-RFB",
                    "bid_description": "Supply and Installation of Smart Meters",
                    "procurement_method": "Request for Bids",
                    "contact_organization": "Nigeria Electricity Regulatory Commission",
                },
                "OP00470002": {
                    "id": "OP00470002",
                    "notice_type": "Invitation for Bids",
                    "publication_date": "2026-07-22",
                    "project_ctry_name": "Nigeria",
                    "project_id": "P170664",
                    "project_name": "Adolescent Girls Initiative for Learning and Empowerment",
                    "description": "Construction of 42 Secondary Schools",
                },
            },
        }
    ).encode("utf-8")


def test_worldbank_procurement_connector_normalizes_notices(monkeypatch):
    raw = _payload()

    async def fake_fetch(url, **kwargs):
        assert url == SOURCE_URL
        assert "application/json" in kwargs["accept"]
        return PublicResource(
            url=url,
            content_type="application/json",
            body=raw,
            encoding="utf-8",
            etag='"wb-v1"',
        )

    monkeypatch.setattr(
        "app.connectors.worldbank_procurement.fetch_public_resource",
        fake_fetch,
    )
    result = asyncio.run(WorldBankProcurementConnector().fetch(SOURCE_URL))

    assert result.connector == "worldbank_procurement"
    assert len(result.documents) == 2
    first = result.documents[0]
    assert first.publisher == "World Bank Group"
    assert first.metadata["notice_id"] == "OP00470001"
    assert first.metadata["country"] == "Nigeria"
    assert first.metadata["project_id"] == "P172891"
    assert "Notice Type: Invitation for Bids" in first.text
    assert "Project: Nigeria Distribution Sector Recovery Program" in first.text
    assert "Description: Supply and Installation of Smart Meters" in first.text
    assert first.canonical_url.endswith("format=json&id=OP00470001")
    assert result.source_raw_sha256 in result.raw_objects


def test_worldbank_procurement_connector_preserves_304(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return PublicResource(
            url=url,
            content_type="",
            body=b"",
            encoding="utf-8",
            status_code=304,
            etag='"wb-v2"',
            last_modified="Wed, 26 Aug 2026 12:00:00 GMT",
        )

    monkeypatch.setattr(
        "app.connectors.worldbank_procurement.fetch_public_resource",
        fake_fetch,
    )
    outcome = asyncio.run(
        WorldBankProcurementConnector().fetch_conditional(
            SOURCE_URL,
            if_none_match='"wb-v1"',
        )
    )
    assert outcome.not_modified is True
    assert outcome.result is None
    assert outcome.etag == '"wb-v2"'


def test_worldbank_procurement_connector_rejects_other_hosts():
    with pytest.raises(ValueError, match="search.worldbank.org"):
        asyncio.run(
            WorldBankProcurementConnector().fetch(
                "https://example.com/api/v2/procnotices?format=json"
            )
        )


def test_registry_exposes_worldbank_procurement_connector():
    assert "worldbank_procurement" in connector_kinds()

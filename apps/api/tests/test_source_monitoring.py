import asyncio
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorFetchOutcome, ConnectorResult, build_document
from app.db import Base, OrganizationRecord, set_tenant_context, utc_now
from app.document_store import LocalDocumentStore
from app.source_db import (
    SourceDocumentRecord,
    SourceFetchRecord,
    SourceScanRunRecord,
    SourceSubscriptionRecord,
)
from app.source_monitoring import (
    SourceSubscriptionCreate,
    claim_manual_scan,
    create_subscription,
    list_subscriptions,
    release_dispatch_claim,
    scan_subscription,
)


def _settings(**overrides):
    values = {
        "source_scan_dispatch_interval_seconds": 60,
        "source_scan_min_interval_seconds": 60,
        "source_scan_lease_seconds": 180,
        "source_scan_max_backoff_seconds": 600,
        "source_scan_auto_pause_failures": 2,
        "source_scan_dispatch_batch_size": 50,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _tenant_session(code: str = "MON"):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    org = OrganizationRecord(name=f"Monitoring {code}", code=code, is_active=True)
    session.add(org)
    session.commit()
    set_tenant_context(session, org.id)
    return engine, session, org.id


def _connector_result(marker: str = "v1") -> ConnectorResult:
    raw = (
        f"<html><head><title>Project {marker}</title></head>"
        f"<body>Port and highway procurement update {marker} "
        + ("A" * 80)
        + "</body></html>"
    ).encode()
    document = build_document(
        connector="html",
        canonical_url="https://8.8.8.8/project",
        title=f"Project {marker}",
        text=f"Port and highway procurement update {marker} " + ("A" * 80),
        content_type="text/html",
        raw=raw,
    )
    return ConnectorResult(
        connector="html",
        source_url="https://8.8.8.8/project",
        source_content_type="text/html",
        source_raw_sha256=document.raw_sha256,
        source_raw_size_bytes=len(raw),
        documents=[document],
        raw_objects={document.raw_sha256: raw},
    )


def test_subscription_scan_archives_change_then_uses_304(monkeypatch, tmp_path):
    monkeypatch.setattr("app.source_monitoring.get_settings", lambda: _settings())
    engine, session, _ = _tenant_session()
    calls: list[tuple[str | None, str | None]] = []
    outcomes = [
        ConnectorFetchOutcome(
            connector="html",
            source_url="https://8.8.8.8/project",
            etag='"v1"',
            last_modified="Mon, 24 Aug 2026 12:00:00 GMT",
            result=_connector_result("v1"),
        ),
        ConnectorFetchOutcome(
            connector="html",
            source_url="https://8.8.8.8/project",
            not_modified=True,
            etag='"v1"',
            last_modified="Mon, 24 Aug 2026 12:00:00 GMT",
        ),
    ]

    async def fake_fetch(kind, url, *, if_none_match=None, if_modified_since=None):
        calls.append((if_none_match, if_modified_since))
        return outcomes.pop(0)

    monkeypatch.setattr("app.source_monitoring.fetch_documents_conditional", fake_fetch)
    record = create_subscription(
        session,
        SourceSubscriptionCreate(
            name="Port procurement",
            connector="html",
            url="https://8.8.8.8/project",
            interval_seconds=60,
        ),
    )
    store = LocalDocumentStore(tmp_path)

    _, token1 = claim_manual_scan(session, record.id)
    first = asyncio.run(
        scan_subscription(
            session,
            record.id,
            manual=True,
            lease_token=token1,
            store=store,
        )
    )
    _, token2 = claim_manual_scan(session, record.id)
    second = asyncio.run(
        scan_subscription(
            session,
            record.id,
            manual=True,
            lease_token=token2,
            store=store,
        )
    )

    assert first.outcome == "changed"
    assert first.documents_created == 1
    assert second.outcome == "not_modified"
    assert second.not_modified is True
    assert calls[0] == (None, None)
    assert calls[1] == ('"v1"', "Mon, 24 Aug 2026 12:00:00 GMT")

    current = session.get(SourceSubscriptionRecord, record.id)
    assert current.total_scans == 2
    assert current.total_changes == 1
    assert current.consecutive_failures == 0
    assert current.etag == '"v1"'
    assert current.lease_token is None
    assert session.scalar(select(func.count()).select_from(SourceFetchRecord)) == 1
    assert session.scalar(select(func.count()).select_from(SourceDocumentRecord)) == 1
    assert session.scalar(select(func.count()).select_from(SourceScanRunRecord)) == 2
    session.close()
    engine.dispose()


def test_failures_backoff_and_auto_pause(monkeypatch):
    monkeypatch.setattr("app.source_monitoring.get_settings", lambda: _settings())
    engine, session, _ = _tenant_session("FAIL")

    async def failing_fetch(*args, **kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr("app.source_monitoring.fetch_documents_conditional", failing_fetch)
    record = create_subscription(
        session,
        SourceSubscriptionCreate(
            name="Unstable feed",
            connector="rss",
            url="https://8.8.8.8/feed.xml",
            interval_seconds=60,
        ),
    )

    _, token1 = claim_manual_scan(session, record.id)
    first = asyncio.run(
        scan_subscription(session, record.id, manual=True, lease_token=token1)
    )
    _, token2 = claim_manual_scan(session, record.id)
    second = asyncio.run(
        scan_subscription(session, record.id, manual=True, lease_token=token2)
    )

    assert first.outcome == "failed"
    assert first.consecutive_failures == 1
    assert first.status == "active"
    assert second.outcome == "failed"
    assert second.consecutive_failures == 2
    assert second.status == "paused"
    current = session.get(SourceSubscriptionRecord, record.id)
    assert current.pause_reason == "automatic_failure_threshold"
    assert current.lease_token is None
    assert current.last_error.startswith("RuntimeError: upstream unavailable")
    assert session.scalar(select(func.count()).select_from(SourceScanRunRecord)) == 2
    session.close()
    engine.dispose()


def test_stale_worker_token_cannot_clear_newer_claim(monkeypatch):
    monkeypatch.setattr("app.source_monitoring.get_settings", lambda: _settings())
    engine, session, _ = _tenant_session("LEASE")
    record = create_subscription(
        session,
        SourceSubscriptionCreate(
            name="Lease fenced feed",
            connector="html",
            url="https://8.8.8.8/lease",
            interval_seconds=60,
        ),
    )
    _, old_token = claim_manual_scan(session, record.id)
    record = session.get(SourceSubscriptionRecord, record.id)
    record.lease_until = utc_now() - timedelta(seconds=1)
    session.commit()
    _, new_token = claim_manual_scan(session, record.id)
    assert new_token != old_token

    async def should_not_fetch(*args, **kwargs):
        raise AssertionError("stale task must be rejected before network I/O")

    monkeypatch.setattr("app.source_monitoring.fetch_documents_conditional", should_not_fetch)
    stale = asyncio.run(
        scan_subscription(session, record.id, manual=True, lease_token=old_token)
    )
    release_dispatch_claim(
        session,
        record.id,
        "old dispatch error",
        lease_token=old_token,
    )

    current = session.get(SourceSubscriptionRecord, record.id)
    assert stale.outcome == "stale_claim"
    assert current.lease_token == new_token
    assert current.lease_until is not None
    session.close()
    engine.dispose()


def test_subscription_orm_reads_are_tenant_scoped(monkeypatch):
    monkeypatch.setattr("app.source_monitoring.get_settings", lambda: _settings())
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as setup:
        org_a = OrganizationRecord(name="Monitoring Org A", code="MON-A", is_active=True)
        org_b = OrganizationRecord(name="Monitoring Org B", code="MON-B", is_active=True)
        setup.add_all([org_a, org_b])
        setup.commit()
        org_a_id, org_b_id = org_a.id, org_b.id

    with Session(engine, expire_on_commit=False) as session_a:
        set_tenant_context(session_a, org_a_id)
        sub_a = create_subscription(
            session_a,
            SourceSubscriptionCreate(
                name="Shared URL A",
                connector="html",
                url="https://8.8.8.8/shared",
                interval_seconds=60,
            ),
        )
        sub_a_id = sub_a.id

    with Session(engine, expire_on_commit=False) as session_b:
        set_tenant_context(session_b, org_b_id)
        sub_b = create_subscription(
            session_b,
            SourceSubscriptionCreate(
                name="Shared URL B",
                connector="html",
                url="https://8.8.8.8/shared",
                interval_seconds=60,
            ),
        )
        sub_b_id = sub_b.id

    with Session(engine) as session_a:
        set_tenant_context(session_a, org_a_id)
        assert [item["id"] for item in list_subscriptions(session_a)] == [sub_a_id]
        assert session_a.get(SourceSubscriptionRecord, sub_b_id) is None

    with Session(engine) as session_b:
        set_tenant_context(session_b, org_b_id)
        assert [item["id"] for item in list_subscriptions(session_b)] == [sub_b_id]
        assert session_b.get(SourceSubscriptionRecord, sub_a_id) is None
    engine.dispose()

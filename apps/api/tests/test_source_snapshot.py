import pytest

from app.source_snapshot import build_source_snapshot, verify_source_snapshot

SAMPLE = {
    "sample_id": "sample-1",
    "source_url": "https://example.com/source",
    "gold_evidence": ["specific procurement notice", "road works"],
}

TEXT = (
    "This Specific Procurement Notice invites bids for road works under the official project. "
    "The notice is published by the project owner."
)


def _snapshot(**overrides):
    values = {
        "origin_source_url": SAMPLE["source_url"],
        "resolved_url": SAMPLE["source_url"],
        "source_title": "Official notice",
        "fetched_at": "2026-08-26T18:00:00+00:00",
        "raw_sha256": "c" * 64,
        "raw_size_bytes": 2048,
        "text": TEXT,
    }
    values.update(overrides)
    return build_source_snapshot(**values)


def test_verified_source_snapshot_accepts_traceable_source():
    snapshot = verify_source_snapshot(SAMPLE, _snapshot())
    assert snapshot.origin_source_url == SAMPLE["source_url"]
    assert snapshot.text == TEXT
    assert len(snapshot.content_sha256) == 64


def test_verified_source_snapshot_rejects_wrong_origin_url():
    with pytest.raises(ValueError, match="origin URL"):
        verify_source_snapshot(
            SAMPLE,
            _snapshot(origin_source_url="https://example.com/other-source"),
        )


def test_verified_source_snapshot_rejects_missing_gold_evidence():
    with pytest.raises(ValueError, match="missing Gold evidence"):
        verify_source_snapshot(SAMPLE, _snapshot(text="This is a different official notice without the required phrases."))


def test_verified_source_snapshot_rejects_tampered_body():
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_source_snapshot(SAMPLE, _snapshot() + "\nchanged after capture")

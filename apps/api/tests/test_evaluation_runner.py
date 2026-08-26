from app.evaluation_runner import evaluate_pipeline_sync
from app.source_snapshot import build_source_snapshot

SAMPLE = {
    "sample_id": "fixture-1",
    "source_name": "Official procurement notice",
    "source_url": "https://example.com/official-notice",
    "country": "Nigeria",
    "sector": "Road",
    "stage": "Invitation for Bids / formal procurement",
    "title": "Nigeria Road Project",
    "owner": "Employer: State Government",
    "financing": "African Development Bank financing received",
    "procurement_signal": "Invitation for Bids published",
    "gold_evidence": ["has received financing from the African Development Bank", "invitation for bids"],
    "must_not_infer": ["win probability", "client preference"],
}

SOURCE_TEXT = (
    "Nigeria road project. Employer: State Government. Invitation for bids. "
    "The borrower has received financing from the African Development Bank."
)


def test_fixture_mode_can_never_be_publishable():
    report = evaluate_pipeline_sync([SAMPLE], use_ai=False, input_mode="fixture")
    assert report.samples_evaluated == 1
    assert report.publishable is False
    assert "严禁" in report.note


def test_source_text_mode_skips_missing_raw_source_and_is_not_publishable():
    report = evaluate_pipeline_sync([SAMPLE], use_ai=False, input_mode="source-text")
    assert report.samples_evaluated == 0
    assert report.samples_skipped == 1
    assert report.publishable is False
    assert report.source_provenance[SAMPLE["sample_id"]] == "missing-snapshot"


def test_embedded_source_text_is_evaluable_but_not_publishable():
    sample = {**SAMPLE, "source_text": SOURCE_TEXT}
    report = evaluate_pipeline_sync([sample], use_ai=False, input_mode="source-text")
    assert report.samples_evaluated == 1
    assert report.samples_skipped == 0
    assert report.publishable is False
    assert report.source_provenance[SAMPLE["sample_id"]] == "embedded-unverified"


def test_source_text_mode_becomes_publishable_only_with_verified_snapshot(tmp_path):
    snapshot = build_source_snapshot(
        origin_source_url=SAMPLE["source_url"],
        resolved_url=SAMPLE["source_url"],
        source_title="Official procurement notice",
        fetched_at="2026-08-26T18:00:00+00:00",
        raw_sha256="a" * 64,
        raw_size_bytes=1024,
        text=SOURCE_TEXT,
    )
    (tmp_path / f"{SAMPLE['sample_id']}.txt").write_text(snapshot, encoding="utf-8")

    report = evaluate_pipeline_sync(
        [SAMPLE],
        use_ai=False,
        input_mode="source-text",
        source_cache_dir=tmp_path,
    )
    assert report.samples_evaluated == 1
    assert report.samples_skipped == 0
    assert report.publishable is True
    assert report.source_provenance[SAMPLE["sample_id"]] == "verified-snapshot"


def test_tampered_snapshot_is_rejected(tmp_path):
    snapshot = build_source_snapshot(
        origin_source_url=SAMPLE["source_url"],
        resolved_url=SAMPLE["source_url"],
        source_title="Official procurement notice",
        fetched_at="2026-08-26T18:00:00+00:00",
        raw_sha256="b" * 64,
        raw_size_bytes=1024,
        text=SOURCE_TEXT,
    )
    tampered = snapshot + " tampered"
    (tmp_path / f"{SAMPLE['sample_id']}.txt").write_text(tampered, encoding="utf-8")

    report = evaluate_pipeline_sync(
        [SAMPLE],
        use_ai=False,
        input_mode="source-text",
        source_cache_dir=tmp_path,
    )
    assert report.samples_evaluated == 0
    assert report.publishable is False
    assert report.source_provenance[SAMPLE["sample_id"]].startswith("invalid-snapshot:")

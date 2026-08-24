from app.evaluation_runner import evaluate_pipeline_sync

SAMPLE = {
    "sample_id": "fixture-1",
    "source_name": "Official procurement notice",
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


def test_source_text_mode_becomes_publishable_only_when_all_samples_have_source_text():
    sample = {
        **SAMPLE,
        "source_text": "Nigeria road project. Employer: State Government. Invitation for bids. The borrower has received financing from the African Development Bank.",
    }
    report = evaluate_pipeline_sync([sample], use_ai=False, input_mode="source-text")
    assert report.samples_evaluated == 1
    assert report.samples_skipped == 0
    assert report.publishable is True

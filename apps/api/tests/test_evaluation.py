from app.evaluation import evaluate_sample, summarize


def test_evaluation_rewards_grounded_output_and_detects_structured_forbidden_inference():
    gold = {
        "sample_id": "x",
        "country": "Nigeria",
        "sector": "Road",
        "stage": "IFB",
        "title": "Road Works",
        "owner": "State PIU",
        "financing": "AfDB financing received",
        "procurement_signal": "Open bidding",
        "gold_evidence": ["AfDB financing received", "Open bidding"],
        "must_not_infer": ["win probability", "client preference"],
    }
    good = {
        "project_detected": True,
        "country": "Nigeria",
        "sector": "Road",
        "stage": "IFB",
        "title": "Road Works",
        "owner": "State PIU",
        "financing": "AfDB financing received",
        "procurement_signal": "Open bidding",
        "notes": "AfDB financing received; Open bidding. Client preference is unknown.",
        "estimated_value_usd_m": None,
        "parties": [],
    }
    result = evaluate_sample(gold, good)
    assert all(result["fields"].values())
    assert all(result["evidence"].values())
    assert result["detection"]["correct"] is True
    assert not any(result["forbidden"].values())

    bad = {
        **good,
        "estimated_value_usd_m": 120,
        "parties": [{"role": "competitor", "name": "Invented Contractor"}],
    }
    result = evaluate_sample(gold, bad)
    assert result["forbidden"]["party_role:competitor"] is True
    assert result["forbidden"]["non_null_field:estimated_value_usd_m"] is True


def test_summary_is_reproducible():
    results = [
        {
            "sample_id": "a",
            "detection": {"expected": True, "predicted": True, "correct": True},
            "fields": {"x": True, "y": False},
            "evidence": {"e": True},
            "forbidden": {"f": False},
        }
    ]
    summary = summarize(results)
    assert summary.detection_accuracy_pct == 100.0
    assert summary.field_accuracy_pct == 50.0
    assert summary.evidence_recall_pct == 100.0
    assert summary.safety_pass_pct == 100.0

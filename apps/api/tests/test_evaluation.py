from app.evaluation import evaluate_sample, summarize


def test_evaluation_rewards_grounded_output_and_detects_forbidden_inference():
    gold={"sample_id":"x","country":"Nigeria","sector":"Road","stage":"IFB","title":"Road Works","owner":"State PIU","financing":"AfDB financing received","procurement_signal":"Open bidding","gold_evidence":["AfDB financing received","Open bidding"],"must_not_infer":["win probability","client preference"]}
    good={**gold,"notes":"AfDB financing received; Open bidding. Client preference is unknown."}
    result=evaluate_sample(gold,good)
    assert all(result["fields"].values())
    assert all(result["evidence"].values())
    # Literal policy labels in structured metadata should not be emitted by a production prediction.
    good.pop("must_not_infer",None); good.pop("gold_evidence",None)
    result=evaluate_sample(gold,good)
    assert result["forbidden"]["win probability"] is False
    assert result["forbidden"]["client preference"] is True


def test_summary_is_reproducible():
    results=[{"sample_id":"a","fields":{"x":True,"y":False},"evidence":{"e":True},"forbidden":{"f":False}}]
    s=summarize(results)
    assert s.field_accuracy_pct==50.0
    assert s.evidence_recall_pct==100.0
    assert s.safety_pass_pct==100.0

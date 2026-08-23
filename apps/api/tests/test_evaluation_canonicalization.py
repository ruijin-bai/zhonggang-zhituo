from app.evaluation import evaluate_sample


def base_gold():
    return {
        "sample_id": "x",
        "country": "Nigeria",
        "sector": "Road / agro-industrial infrastructure",
        "stage": "Invitation for Bids / formal procurement",
        "title": "Construction of 32Km Connecting Roads",
        "owner": "State Government",
        "financing": "African Development Bank financing received",
        "procurement_signal": "Open Competitive Bidding (International)",
        "gold_evidence": [],
        "must_not_infer": [],
    }


def test_sector_and_stage_are_compared_by_business_category():
    gold = base_gold()
    prediction = {
        "country": "Nigeria",
        "sector": "Road",
        "stage": "Invitation for Bids",
        "title": "Construction of 32Km Connecting Roads",
        "owner": "State Government",
        "financing": "financing received",
        "procurement_signal": "formal procurement / invitation for bids",
    }
    result = evaluate_sample(gold, prediction)
    assert result["fields"]["sector"] is True
    assert result["fields"]["stage"] is True
    assert result["fields"]["financing"] is True
    assert result["fields"]["procurement_signal"] is True


def test_title_requires_strong_overlap_not_any_keyword():
    gold = base_gold()
    prediction = {
        "country": "Nigeria",
        "sector": "Road",
        "stage": "Invitation for Bids",
        "title": "Road Project",
        "owner": "State Government",
        "financing": "financing received",
        "procurement_signal": "Invitation for Bids",
    }
    result = evaluate_sample(gold, prediction)
    assert result["fields"]["title"] is False

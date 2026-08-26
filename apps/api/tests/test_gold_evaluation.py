from pathlib import Path

from app.ai import _deterministic_project
from app.evaluation import evaluate_sample, summarize
from app.gold_dataset import load_gold_dataset, validate_gold_dataset

ROOT = Path(__file__).resolve().parents[3]


def test_gold_loader_includes_extensions_and_regression_negatives() -> None:
    samples = load_gold_dataset(
        ROOT,
        include_extensions=True,
        include_regression_negatives=True,
    )
    validation = validate_gold_dataset(samples)

    assert validation.positives == 13
    assert validation.negatives == 4
    assert validation.samples == 17
    assert validation.countries >= 8
    assert validation.evidence_items > 20


def test_financial_report_does_not_match_port_substring() -> None:
    discovery = _deterministic_project(
        "The annual financial report summarizes treasury operations and audited accounts.",
        "Annual financial report",
    )
    assert discovery.project_detected is False
    assert discovery.sector == "待识别"


def test_structured_safety_detects_unsupported_party_and_amount() -> None:
    gold = {
        "sample_id": "safety-sample",
        "project_expected": True,
        "country": "Nigeria",
        "sector": "Road",
        "stage": "Invitation for Bids",
        "title": "Road works",
        "owner": "Not established in this gold record",
        "financing": "Not asserted beyond official publication",
        "procurement_signal": "IFB published",
        "gold_evidence": ["Road works"],
        "must_not_infer": ["competitor identity", "contract value"],
    }
    prediction = {
        "project_detected": True,
        "country": "Nigeria",
        "sector": "Road",
        "stage": "formal procurement",
        "title": "Road works",
        "owner": "待识别",
        "financing": "待核实",
        "procurement_signal": "Invitation for Bids published",
        "estimated_value_usd_m": 120,
        "parties": [
            {
                "role": "competitor",
                "name": "Invented Contractor",
                "evidence_quote": "",
            }
        ],
    }

    result = evaluate_sample(gold, prediction)
    assert result["fields"]["owner"] is True
    assert result["forbidden"]["party_role:competitor"] is True
    assert result["forbidden"]["non_null_field:estimated_value_usd_m"] is True

    summary = summarize([result])
    assert summary.detection_accuracy_pct == 100.0
    assert summary.safety_pass_pct < 100.0


def test_unknown_is_not_penalized_as_a_hallucinated_owner() -> None:
    gold = {
        "sample_id": "unknown-owner",
        "project_expected": True,
        "country": "Ghana",
        "sector": "Bridge",
        "stage": "Specific Procurement Notice",
        "title": "Bridge works",
        "owner": "Not established in this gold record",
        "financing": "Not asserted beyond official publication",
        "procurement_signal": "SPN published",
        "gold_evidence": ["Bridge works"],
        "must_not_infer": ["client preference"],
    }
    prediction = {
        "project_detected": True,
        "country": "Ghana",
        "sector": "桥梁工程",
        "stage": "正式采购/招标临近",
        "title": "Bridge works",
        "owner": "待识别",
        "financing": "待核实",
        "procurement_signal": "procurement notice",
        "estimated_value_usd_m": None,
        "parties": [],
    }

    result = evaluate_sample(gold, prediction)
    assert result["fields"]["owner"] is True
    assert result["fields"]["financing"] is True
    assert result["fields"]["stage"] is True
    assert result["fields"]["procurement_signal"] is True
    assert not any(result["forbidden"].values())

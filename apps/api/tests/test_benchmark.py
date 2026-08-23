from app.benchmark import calculate_benchmark


def test_calculate_benchmark_from_paired_samples():
    metrics = calculate_benchmark([
        {"manual_seconds": 600, "zhituo_seconds": 120, "fields_correct": 8, "fields_total": 10, "evidence_traced": 9, "evidence_total": 10, "decision_match": True},
        {"manual_seconds": 900, "zhituo_seconds": 180, "fields_correct": 9, "fields_total": 10, "evidence_traced": 10, "evidence_total": 10, "decision_match": False},
    ])
    assert metrics.samples == 2
    assert metrics.manual_minutes == 25.0
    assert metrics.zhituo_minutes == 5.0
    assert metrics.time_saved_minutes == 20.0
    assert metrics.efficiency_gain_pct == 80.0
    assert metrics.field_precision_pct == 85.0
    assert metrics.evidence_traceability_pct == 95.0
    assert metrics.decision_agreement_pct == 50.0


def test_empty_benchmark_is_zero_not_fabricated():
    metrics = calculate_benchmark([])
    assert metrics.samples == 0
    assert metrics.efficiency_gain_pct == 0

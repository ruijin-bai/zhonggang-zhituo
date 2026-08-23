from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkMetrics:
    samples: int
    manual_minutes: float
    zhituo_minutes: float
    time_saved_minutes: float
    efficiency_gain_pct: float
    field_precision_pct: float
    evidence_traceability_pct: float
    decision_agreement_pct: float


def _pct(numerator: float, denominator: float) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def calculate_benchmark(rows: list[dict]) -> BenchmarkMetrics:
    """Aggregate paired manual-vs-Zhituo evaluation rows.

    Required row keys:
    manual_seconds, zhituo_seconds, fields_correct, fields_total,
    evidence_traced, evidence_total, decision_match.
    """
    if not rows:
        return BenchmarkMetrics(0, 0, 0, 0, 0, 0, 0, 0)

    manual_seconds = sum(float(row["manual_seconds"]) for row in rows)
    zhituo_seconds = sum(float(row["zhituo_seconds"]) for row in rows)
    fields_correct = sum(int(row["fields_correct"]) for row in rows)
    fields_total = sum(int(row["fields_total"]) for row in rows)
    evidence_traced = sum(int(row["evidence_traced"]) for row in rows)
    evidence_total = sum(int(row["evidence_total"]) for row in rows)
    decision_matches = sum(1 for row in rows if bool(row["decision_match"]))

    manual_minutes = round(manual_seconds / 60, 1)
    zhituo_minutes = round(zhituo_seconds / 60, 1)
    saved = max(0.0, manual_seconds - zhituo_seconds)
    return BenchmarkMetrics(
        samples=len(rows),
        manual_minutes=manual_minutes,
        zhituo_minutes=zhituo_minutes,
        time_saved_minutes=round(saved / 60, 1),
        efficiency_gain_pct=_pct(saved, manual_seconds),
        field_precision_pct=_pct(fields_correct, fields_total),
        evidence_traceability_pct=_pct(evidence_traced, evidence_total),
        decision_agreement_pct=_pct(decision_matches, len(rows)),
    )

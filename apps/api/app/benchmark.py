from dataclasses import dataclass
from urllib.parse import urlparse


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


def validate_benchmark_rows(rows: list[dict]) -> None:
    """Reject malformed real-pilot rows before any business metric is calculated."""
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id:
            raise ValueError(f"row {index}: sample_id is required")
        if sample_id in seen:
            raise ValueError(f"row {index}: duplicate sample_id {sample_id}")
        seen.add(sample_id)

        source_url = str(row.get("source_url") or "").strip()
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"row {index}: source_url must be an absolute HTTPS URL")
        if not str(row.get("reviewer") or "").strip():
            raise ValueError(f"row {index}: reviewer is required")

        try:
            manual_seconds = float(row["manual_seconds"])
            zhituo_seconds = float(row["zhituo_seconds"])
            fields_correct = int(row["fields_correct"])
            fields_total = int(row["fields_total"])
            evidence_traced = int(row["evidence_traced"])
            evidence_total = int(row["evidence_total"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"row {index}: benchmark numeric fields are invalid") from exc

        if manual_seconds <= 0 or zhituo_seconds <= 0:
            raise ValueError(f"row {index}: elapsed seconds must be positive")
        if fields_total <= 0 or not 0 <= fields_correct <= fields_total:
            raise ValueError(f"row {index}: fields_correct/fields_total is invalid")
        if evidence_total <= 0 or not 0 <= evidence_traced <= evidence_total:
            raise ValueError(f"row {index}: evidence_traced/evidence_total is invalid")
        if not isinstance(row.get("decision_match"), bool):
            raise ValueError(f"row {index}: decision_match must be boolean")


def calculate_benchmark(rows: list[dict]) -> BenchmarkMetrics:
    """Aggregate paired manual-vs-Zhituo evaluation rows."""
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

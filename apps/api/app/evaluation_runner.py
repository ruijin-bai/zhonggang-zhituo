import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path

from .ai import AIService
from .evaluation import evaluate_sample, summarize
from .source_snapshot import verify_source_snapshot


@dataclass(frozen=True)
class PipelineEvaluationReport:
    mode: str
    publishable: bool
    samples_total: int
    samples_evaluated: int
    samples_skipped: int
    extraction_modes: dict[str, int]
    source_provenance: dict[str, str]
    summary: dict
    results: list[dict]
    note: str


def _fixture_text(sample: dict) -> str:
    """Gold-derived or explicitly synthetic engineering fixture; never a business-accuracy input."""
    explicit = str(sample.get("fixture_text") or "").strip()
    if explicit:
        return explicit
    parts = [
        f"Country: {sample.get('country', '')}",
        f"Project: {sample.get('title', '')}",
        f"Sector: {sample.get('sector', '')}",
        f"Owner: {sample.get('owner', '')}",
        f"Stage: {sample.get('stage', '')}",
        f"Financing: {sample.get('financing', '')}",
        f"Procurement: {sample.get('procurement_signal', '')}",
    ]
    parts.extend(sample.get("gold_evidence", []))
    return "\n".join(part for part in parts if part)


def _source_input(
    sample: dict,
    source_cache_dir: Path | None,
) -> tuple[str, str, str]:
    """Load source text and classify whether it is cryptographically traceable."""

    fallback_title = str(sample.get("source_name") or "公开来源").strip() or "公开来源"
    embedded = str(sample.get("source_text") or "").strip()
    if embedded:
        page_title = str(sample.get("source_page_title") or fallback_title).strip() or fallback_title
        return embedded, page_title, "embedded-unverified"

    if source_cache_dir:
        path = source_cache_dir / f"{sample['sample_id']}.txt"
        if path.exists():
            try:
                snapshot = verify_source_snapshot(sample, path.read_text(encoding="utf-8"))
            except Exception as exc:
                return "", fallback_title, f"invalid-snapshot: {exc}"
            return snapshot.text, snapshot.source_title or fallback_title, "verified-snapshot"

    return "", fallback_title, "missing-snapshot"


def _procurement_signal(discovery) -> str:
    maturity = next((x for x in discovery.facts if x.field_name == "project_maturity"), None)
    if maturity is None:
        return discovery.stage
    quote = (maturity.evidence_quote or "").lower()
    if "specific procurement notice" in quote or " spn " in f" {quote} ":
        return "SPN published"
    if any(term in quote for term in ("invitation for bids", "invitation to bid", "open competitive bidding")):
        return "Invitation for Bids published"
    if "procurement plan" in quote or " ppm " in f" {quote} ":
        return "Procurement plan published"
    return maturity.value


def _prediction_from_discovery(discovery) -> dict:
    facts = list(discovery.facts)
    financing = next((x for x in facts if x.field_name == "financing"), None)
    return {
        "country": discovery.country,
        "sector": discovery.sector,
        "stage": discovery.stage,
        "title": discovery.title,
        "owner": discovery.owner,
        "financing": financing.value if financing else "待核实",
        "procurement_signal": _procurement_signal(discovery),
        "project_detected": discovery.project_detected,
        "estimated_value_usd_m": discovery.estimated_value_usd_m,
        "confidence": discovery.confidence,
        "evidence_quotes": [x.evidence_quote for x in facts if x.evidence_quote],
        "parties": [
            {
                "role": party.role,
                "name": party.name,
                "country": party.country,
                "evidence_quote": party.evidence_quote,
                "confidence": party.confidence,
            }
            for party in discovery.parties
        ],
    }


async def evaluate_pipeline(
    samples: list[dict],
    *,
    use_ai: bool = False,
    input_mode: str = "source-text",
    service: AIService | None = None,
    source_cache_dir: Path | None = None,
) -> PipelineEvaluationReport:
    if input_mode not in {"source-text", "fixture"}:
        raise ValueError("input_mode must be 'source-text' or 'fixture'")
    service = service or AIService()
    results = []
    modes: dict[str, int] = {}
    provenance: dict[str, str] = {}
    skipped = 0
    for sample in samples:
        sample_id = str(sample.get("sample_id") or "unknown")
        if input_mode == "source-text":
            text, page_title, source_status = _source_input(sample, source_cache_dir)
            provenance[sample_id] = source_status
        else:
            text = _fixture_text(sample)
            page_title = sample.get("title") or sample.get("source_name") or "公开来源"
            provenance[sample_id] = "fixture"
        if not text:
            skipped += 1
            continue
        discovery, mode = await service.discover_project(
            text,
            page_title=page_title,
            use_ai=use_ai,
        )
        modes[mode] = modes.get(mode, 0) + 1
        prediction = _prediction_from_discovery(discovery)
        item = evaluate_sample(sample, prediction)
        item["prediction"] = prediction
        item["extraction_mode"] = mode
        item["source_provenance"] = provenance[sample_id]
        results.append(item)
    summary = asdict(summarize(results))
    contains_synthetic = any(
        sample.get("sample_kind") == "synthetic-regression" for sample in samples
    )
    all_sources_verified = bool(samples) and all(
        provenance.get(str(sample.get("sample_id") or "unknown")) == "verified-snapshot"
        for sample in samples
    )
    publishable = (
        input_mode == "source-text"
        and skipped == 0
        and bool(results)
        and not contains_synthetic
        and all_sources_verified
    )
    note = (
        "全部输入来自 URL 对应、正文 SHA-256 自校验且 Gold evidence 可复核的来源快照，可用于正式评测。"
        if publishable
        else (
            "fixture 模式仅用于工程回归，输入由 Gold 字段或显式合成负样本构造，严禁将该结果作为比赛或业务准确率。"
            if input_mode == "fixture"
            else (
                "当前评测包含 synthetic-regression 样本，严禁标记为正式准确率。"
                if contains_synthetic
                else "真实来源输入尚未全部通过 snapshot provenance 校验；当前结果不可作为正式准确率。"
            )
        )
    )
    return PipelineEvaluationReport(
        input_mode,
        publishable,
        len(samples),
        len(results),
        skipped,
        modes,
        provenance,
        summary,
        results,
        note,
    )


def evaluate_pipeline_sync(samples: list[dict], **kwargs) -> PipelineEvaluationReport:
    return asyncio.run(evaluate_pipeline(samples, **kwargs))

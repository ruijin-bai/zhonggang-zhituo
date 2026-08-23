import asyncio
from dataclasses import asdict, dataclass

from .ai import AIService
from .evaluation import evaluate_sample, summarize


@dataclass(frozen=True)
class PipelineEvaluationReport:
    mode: str
    publishable: bool
    samples_total: int
    samples_evaluated: int
    samples_skipped: int
    extraction_modes: dict[str, int]
    summary: dict
    results: list[dict]
    note: str


def _fixture_text(sample: dict) -> str:
    """Build a deterministic regression fixture from gold metadata.

    This is deliberately NOT a real-world accuracy benchmark. It exists to verify
    pipeline wiring and regression behavior until cached source text is available.
    """
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


def _prediction_from_discovery(discovery) -> dict:
    facts = list(discovery.facts)
    financing_fact = next((fact for fact in facts if fact.field_name == "financing"), None)
    maturity_fact = next((fact for fact in facts if fact.field_name == "project_maturity"), None)
    evidence_quotes = [fact.evidence_quote for fact in facts if fact.evidence_quote]
    return {
        "country": discovery.country,
        "sector": discovery.sector,
        "stage": discovery.stage,
        "title": discovery.title,
        "owner": discovery.owner,
        "financing": financing_fact.value if financing_fact else "待核实",
        "procurement_signal": maturity_fact.value if maturity_fact else discovery.stage,
        "project_detected": discovery.project_detected,
        "confidence": discovery.confidence,
        "evidence_quotes": evidence_quotes,
    }


async def evaluate_pipeline(
    samples: list[dict],
    *,
    use_ai: bool = False,
    input_mode: str = "source-text",
    service: AIService | None = None,
) -> PipelineEvaluationReport:
    if input_mode not in {"source-text", "fixture"}:
        raise ValueError("input_mode must be 'source-text' or 'fixture'")
    service = service or AIService()
    results: list[dict] = []
    modes: dict[str, int] = {}
    skipped = 0

    for sample in samples:
        if input_mode == "source-text":
            text = str(sample.get("source_text") or "").strip()
            if not text:
                skipped += 1
                continue
        else:
            text = _fixture_text(sample)

        discovery, extraction_mode = await service.discover_project(
            text,
            page_title=sample.get("title") or sample.get("source_name") or "公开来源",
            use_ai=use_ai,
        )
        modes[extraction_mode] = modes.get(extraction_mode, 0) + 1
        prediction = _prediction_from_discovery(discovery)
        item = evaluate_sample(sample, prediction)
        item["prediction"] = prediction
        item["extraction_mode"] = extraction_mode
        results.append(item)

    summary = asdict(summarize(results))
    publishable = input_mode == "source-text" and skipped == 0 and bool(results)
    note = (
        "基于缓存的真实来源正文，可用于正式评测。"
        if publishable
        else (
            "fixture 模式仅用于工程回归，输入由 Gold 字段构造，严禁将该结果作为比赛准确率。"
            if input_mode == "fixture"
            else "部分或全部样本缺少 source_text；当前结果不可作为正式准确率。"
        )
    )
    return PipelineEvaluationReport(
        mode=input_mode,
        publishable=publishable,
        samples_total=len(samples),
        samples_evaluated=len(results),
        samples_skipped=skipped,
        extraction_modes=modes,
        summary=summary,
        results=results,
        note=note,
    )


def evaluate_pipeline_sync(samples: list[dict], **kwargs) -> PipelineEvaluationReport:
    return asyncio.run(evaluate_pipeline(samples, **kwargs))

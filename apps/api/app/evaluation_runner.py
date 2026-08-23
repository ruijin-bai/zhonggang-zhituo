import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path

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
    """Gold-derived engineering fixture; never a real-world accuracy input."""
    parts = [f"Country: {sample.get('country','')}", f"Project: {sample.get('title','')}", f"Sector: {sample.get('sector','')}", f"Owner: {sample.get('owner','')}", f"Stage: {sample.get('stage','')}", f"Financing: {sample.get('financing','')}", f"Procurement: {sample.get('procurement_signal','')}"]
    parts.extend(sample.get("gold_evidence", []))
    return "\n".join(part for part in parts if part)


def _source_text(sample: dict, source_cache_dir: Path | None) -> str:
    embedded = str(sample.get("source_text") or "").strip()
    if embedded:
        return embedded
    if source_cache_dir:
        path = source_cache_dir / f"{sample['sample_id']}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return ""


def _prediction_from_discovery(discovery) -> dict:
    facts=list(discovery.facts); financing=next((x for x in facts if x.field_name=="financing"),None); maturity=next((x for x in facts if x.field_name=="project_maturity"),None)
    return {"country":discovery.country,"sector":discovery.sector,"stage":discovery.stage,"title":discovery.title,"owner":discovery.owner,"financing":financing.value if financing else "待核实","procurement_signal":maturity.value if maturity else discovery.stage,"project_detected":discovery.project_detected,"confidence":discovery.confidence,"evidence_quotes":[x.evidence_quote for x in facts if x.evidence_quote]}


async def evaluate_pipeline(samples:list[dict],*,use_ai:bool=False,input_mode:str="source-text",service:AIService|None=None,source_cache_dir:Path|None=None)->PipelineEvaluationReport:
    if input_mode not in {"source-text","fixture"}:raise ValueError("input_mode must be 'source-text' or 'fixture'")
    service=service or AIService();results=[];modes={};skipped=0
    for sample in samples:
        text=_source_text(sample,source_cache_dir) if input_mode=="source-text" else _fixture_text(sample)
        if not text:skipped+=1;continue
        discovery,mode=await service.discover_project(text,page_title=sample.get("title") or sample.get("source_name") or "公开来源",use_ai=use_ai)
        modes[mode]=modes.get(mode,0)+1;prediction=_prediction_from_discovery(discovery);item=evaluate_sample(sample,prediction);item["prediction"]=prediction;item["extraction_mode"]=mode;results.append(item)
    summary=asdict(summarize(results));publishable=input_mode=="source-text" and skipped==0 and bool(results)
    note="基于缓存的真实来源正文，可用于正式评测。" if publishable else ("fixture 模式仅用于工程回归，输入由 Gold 字段构造，严禁将该结果作为比赛准确率。" if input_mode=="fixture" else "部分或全部样本缺少真实来源正文缓存；当前结果不可作为正式准确率。")
    return PipelineEvaluationReport(input_mode,publishable,len(samples),len(results),skipped,modes,summary,results,note)


def evaluate_pipeline_sync(samples:list[dict],**kwargs)->PipelineEvaluationReport:return asyncio.run(evaluate_pipeline(samples,**kwargs))

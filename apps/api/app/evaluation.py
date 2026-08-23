from dataclasses import dataclass, asdict
from collections import Counter


@dataclass(frozen=True)
class EvaluationSummary:
    samples: int
    field_checks: int
    field_correct: int
    field_accuracy_pct: float
    evidence_checks: int
    evidence_hits: int
    evidence_recall_pct: float
    forbidden_inference_checks: int
    forbidden_inference_violations: int
    safety_pass_pct: float


def _pct(a:int,b:int)->float:
    return round(a/b*100,1) if b else 0.0


def normalize(value: object) -> str:
    return " ".join(str(value or "").lower().replace("–","-").replace("—","-").split())


def evaluate_sample(gold:dict, prediction:dict)->dict:
    fields=["country","sector","stage","title","owner","financing","procurement_signal"]
    field_results={k: normalize(gold.get(k)) == normalize(prediction.get(k)) for k in fields}
    predicted_text=normalize(prediction)
    evidence_results={e: normalize(e) in predicted_text for e in gold.get("gold_evidence",[])}
    forbidden_results={x: normalize(x) in predicted_text for x in gold.get("must_not_infer",[])}
    return {"sample_id":gold["sample_id"],"fields":field_results,"evidence":evidence_results,"forbidden":forbidden_results}


def summarize(results:list[dict])->EvaluationSummary:
    field_checks=sum(len(r["fields"]) for r in results); field_correct=sum(sum(r["fields"].values()) for r in results)
    evidence_checks=sum(len(r["evidence"]) for r in results); evidence_hits=sum(sum(r["evidence"].values()) for r in results)
    forbidden_checks=sum(len(r["forbidden"]) for r in results); violations=sum(sum(r["forbidden"].values()) for r in results)
    return EvaluationSummary(len(results),field_checks,field_correct,_pct(field_correct,field_checks),evidence_checks,evidence_hits,_pct(evidence_hits,evidence_checks),forbidden_checks,violations,_pct(forbidden_checks-violations,forbidden_checks))


def report_dict(results:list[dict])->dict:
    return {"summary":asdict(summarize(results)),"results":results}

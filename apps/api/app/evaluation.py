from dataclasses import dataclass, asdict
import re


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


def _pct(a: int, b: int) -> float:
    return round(a / b * 100, 1) if b else 0.0


def normalize(value: object) -> str:
    return " ".join(str(value or "").lower().replace("–", "-").replace("—", "-").split())


def _canonical_sector(value: object) -> str:
    text = normalize(value)
    rules = [
        (("dredg", "疏浚"), "dredging"),
        (("port", "terminal", "quay", "港口", "码头"), "port"),
        (("bridge", "桥"), "bridge"),
        (("rail", "train", "铁路", "轨道"), "rail"),
        (("water", "pipe", "供水", "水务"), "water"),
        (("transmission", "substation", "power", "输电", "变电"), "power"),
        (("irrigation", "灌溉"), "irrigation"),
        (("airport", "机场"), "airport"),
        (("road", "highway", "route", "道路", "公路"), "road"),
    ]
    for keywords, label in rules:
        if any(keyword in text for keyword in keywords):
            return label
    return text


def _canonical_stage(value: object) -> str:
    text = normalize(value)
    if any(term in text for term in ("invitation for bids", "ifb", "formal procurement", "open competitive bidding", "正式招标", "投标邀请")):
        return "ifb"
    if any(term in text for term in ("specific procurement notice", "spn", "采购公告")):
        return "spn"
    if any(term in text for term in ("procurement plan", "ppm", "采购计划")):
        return "procurement-plan"
    if any(term in text for term in ("feasibility", "可研")):
        return "feasibility"
    return text


def _financing_class(value: object) -> str:
    text = normalize(value)
    if any(term in text for term in ("received financing", "financing received", "loan approved", "financing approved", "融资获批", "已获融资")):
        return "confirmed"
    if any(term in text for term in ("loan agreement", "financing agreement", "融资协议", "融资谈判")):
        return "structured"
    if any(term in text for term in ("not asserted", "待核实", "unknown")):
        return "unknown"
    return text


def _field_match(field: str, gold_value: object, predicted_value: object) -> bool:
    if field == "sector":
        return _canonical_sector(gold_value) == _canonical_sector(predicted_value)
    if field in {"stage", "procurement_signal"}:
        return _canonical_stage(gold_value) == _canonical_stage(predicted_value)
    if field == "financing":
        return _financing_class(gold_value) == _financing_class(predicted_value)
    if field == "title":
        gold = normalize(gold_value)
        pred = normalize(predicted_value)
        if not gold or not pred:
            return False
        # Titles can carry punctuation/subtitle differences; require strong token overlap.
        gold_tokens = set(re.findall(r"[a-z0-9]+", gold))
        pred_tokens = set(re.findall(r"[a-z0-9]+", pred))
        if not gold_tokens or not pred_tokens:
            return gold == pred
        return len(gold_tokens & pred_tokens) / len(gold_tokens) >= 0.8
    return normalize(gold_value) == normalize(predicted_value)


def evaluate_sample(gold: dict, prediction: dict) -> dict:
    fields = ["country", "sector", "stage", "title", "owner", "financing", "procurement_signal"]
    field_results = {key: _field_match(key, gold.get(key), prediction.get(key)) for key in fields}
    predicted_text = normalize(prediction)
    evidence_results = {e: normalize(e) in predicted_text for e in gold.get("gold_evidence", [])}
    forbidden_results = {x: normalize(x) in predicted_text for x in gold.get("must_not_infer", [])}
    return {"sample_id": gold["sample_id"], "fields": field_results, "evidence": evidence_results, "forbidden": forbidden_results}


def summarize(results: list[dict]) -> EvaluationSummary:
    field_checks = sum(len(r["fields"]) for r in results)
    field_correct = sum(sum(r["fields"].values()) for r in results)
    evidence_checks = sum(len(r["evidence"]) for r in results)
    evidence_hits = sum(sum(r["evidence"].values()) for r in results)
    forbidden_checks = sum(len(r["forbidden"]) for r in results)
    violations = sum(sum(r["forbidden"].values()) for r in results)
    return EvaluationSummary(
        len(results),
        field_checks,
        field_correct,
        _pct(field_correct, field_checks),
        evidence_checks,
        evidence_hits,
        _pct(evidence_hits, evidence_checks),
        forbidden_checks,
        violations,
        _pct(forbidden_checks - violations, forbidden_checks),
    )


def report_dict(results: list[dict]) -> dict:
    return {"summary": asdict(summarize(results)), "results": results}

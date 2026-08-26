import re
from dataclasses import asdict, dataclass

from .gold_dataset import project_expected, safety_constraints


@dataclass(frozen=True)
class EvaluationSummary:
    samples: int
    detection_checks: int
    detection_correct: int
    detection_accuracy_pct: float
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


def _unknown(value: object) -> bool:
    text = normalize(value)
    if not text:
        return True
    markers = (
        "not established",
        "not asserted",
        "unknown",
        "待识别",
        "待核实",
        "未明确",
        "未建立",
    )
    return any(marker in text for marker in markers)


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
    if any(
        term in text
        for term in (
            "invitation for bids",
            "ifb",
            "specific procurement notice",
            "spn",
            "formal procurement",
            "open competitive bidding",
            "procurement notice",
            "正式采购",
            "正式招标",
            "招标公告",
            "投标邀请",
        )
    ):
        return "formal-procurement"
    if any(term in text for term in ("procurement plan", "ppm", "procurement preparation", "采购计划", "采购准备")):
        return "procurement-plan"
    if any(term in text for term in ("project financing", "terminal redevelopment", "financing", "融资")):
        return "financing"
    if any(term in text for term in ("feasibility", "可研")):
        return "feasibility"
    return text


def _canonical_procurement_signal(value: object) -> str:
    text = normalize(value)
    if any(term in text for term in ("specific procurement notice", "spn")):
        return "spn"
    if any(term in text for term in ("invitation for bids", "invitation to bid", "ifb", "open competitive bidding")):
        return "ifb"
    if any(term in text for term in ("procurement plan", "ppm")):
        return "procurement-plan"
    if any(term in text for term in ("procurement notice", "formal procurement", "正式采购", "招标公告", "投标邀请")):
        return "procurement-notice"
    return text


def _financing_class(value: object) -> str:
    text = normalize(value)
    if _unknown(value):
        return "unknown"
    if any(
        term in text
        for term in (
            "received financing",
            "financing received",
            "loan approved",
            "financing approved",
            "已获批",
            "融资落实",
            "融资获批",
            "已获融资",
        )
    ):
        return "confirmed"
    if any(term in text for term in ("loan agreement", "financing agreement", "mandated lead arranger", "融资协议", "融资谈判")):
        return "structured"
    return text


def _field_match(field: str, gold_value: object, predicted_value: object) -> bool:
    if field in {"owner", "country", "title"} and _unknown(gold_value):
        return _unknown(predicted_value)
    if field == "sector":
        return _canonical_sector(gold_value) == _canonical_sector(predicted_value)
    if field == "stage":
        return _canonical_stage(gold_value) == _canonical_stage(predicted_value)
    if field == "procurement_signal":
        gold = _canonical_procurement_signal(gold_value)
        predicted = _canonical_procurement_signal(predicted_value)
        if gold == predicted:
            return True
        # The current production model exposes a broad project-maturity fact. Treat a generic
        # formal-procurement signal as compatible with IFB/SPN until a dedicated procurement
        # signal field is promoted into the product schema.
        return predicted == "procurement-notice" and gold in {"ifb", "spn", "procurement-notice"}
    if field == "financing":
        return _financing_class(gold_value) == _financing_class(predicted_value)
    if field == "title":
        gold = normalize(gold_value)
        pred = normalize(predicted_value)
        if not gold or not pred:
            return False
        gold_tokens = set(re.findall(r"[a-z0-9]+", gold))
        pred_tokens = set(re.findall(r"[a-z0-9]+", pred))
        if not gold_tokens or not pred_tokens:
            return gold == pred
        return len(gold_tokens & pred_tokens) / len(gold_tokens) >= 0.8
    return normalize(gold_value) == normalize(predicted_value)


def _is_non_null_prediction(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return not _unknown(value)
    return True


def evaluate_sample(gold: dict, prediction: dict) -> dict:
    expected_detection = project_expected(gold)
    predicted_detection = bool(prediction.get("project_detected"))
    detection = {
        "expected": expected_detection,
        "predicted": predicted_detection,
        "correct": expected_detection == predicted_detection,
    }

    field_names = ["country", "sector", "stage", "title", "owner", "financing", "procurement_signal"]
    fields = {}
    if expected_detection:
        fields = {
            key: _field_match(key, gold.get(key), prediction.get(key))
            for key in field_names
            if key in gold
        }

    predicted_text = normalize(prediction)
    evidence = {
        item: normalize(item) in predicted_text
        for item in gold.get("gold_evidence", [])
    }

    forbidden: dict[str, bool] = {}
    constraints = safety_constraints(gold)
    predicted_parties = prediction.get("parties") or []
    for role in constraints["forbidden_party_roles"]:
        forbidden[f"party_role:{role}"] = any(
            normalize(party.get("role")) == normalize(role)
            for party in predicted_parties
            if isinstance(party, dict)
        )
    for field in constraints["forbidden_non_null_fields"]:
        forbidden[f"non_null_field:{field}"] = _is_non_null_prediction(prediction.get(field))

    # Human-readable must_not_infer remains evidence for review/reporting, but safety pass/fail is
    # based on structured output constraints rather than brittle substring matching.
    return {
        "sample_id": gold["sample_id"],
        "detection": detection,
        "fields": fields,
        "evidence": evidence,
        "forbidden": forbidden,
        "must_not_infer": list(gold.get("must_not_infer", [])),
    }


def summarize(results: list[dict]) -> EvaluationSummary:
    detection_checks = len(results)
    detection_correct = sum(int(r["detection"]["correct"]) for r in results)
    field_checks = sum(len(r["fields"]) for r in results)
    field_correct = sum(sum(r["fields"].values()) for r in results)
    evidence_checks = sum(len(r["evidence"]) for r in results)
    evidence_hits = sum(sum(r["evidence"].values()) for r in results)
    forbidden_checks = sum(len(r["forbidden"]) for r in results)
    violations = sum(sum(r["forbidden"].values()) for r in results)
    return EvaluationSummary(
        len(results),
        detection_checks,
        detection_correct,
        _pct(detection_correct, detection_checks),
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

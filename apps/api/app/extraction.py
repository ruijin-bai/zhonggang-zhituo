import re

from .models import ExtractedFact, SourceExtraction

FINANCING_RULES: list[tuple[tuple[str, ...], str, int, float]] = [
    (
        (
            "has received financing",
            "received financing from",
            "loan approved",
            "approved the loan",
            "board approved the loan",
            "financing approved",
            "approved financing",
            "verified financing",
            "贷款获批",
            "融资获批",
            "批准贷款",
            "董事会批准",
            "已获得融资",
        ),
        "已获批或融资落实",
        15,
        0.96,
    ),
    (
        (
            "financing agreement",
            "loan agreement",
            "融资框架",
            "贷款协议",
            "贷款谈判",
            "融资谈判",
        ),
        "融资框架/贷款谈判明确",
        11,
        0.88,
    ),
    (
        (
            "financial institution",
            "financier engagement",
            "金融机构接触",
            "融资接触",
        ),
        "已与金融机构接触",
        8,
        0.78,
    ),
]

MATURITY_RULES: list[tuple[tuple[str, ...], str, int, float]] = [
    (
        (
            "invitation for bids",
            "invitations for bids",
            "invitation to bid",
            "invitations to bid",
            "tender notice",
            "request for bids",
            "formal procurement-stage",
            "formal procurement",
            "正式招标",
            "招标公告",
            "投标邀请",
        ),
        "正式采购/招标临近",
        15,
        0.96,
    ),
    (
        (
            "procurement plan",
            "procurement preparation",
            "采购计划",
            "采购准备",
        ),
        "融资与采购准备中",
        13,
        0.92,
    ),
    (("feasibility study completed", "可研完成"), "可研完成/预算明确", 10, 0.90),
    (("feasibility study", "可研启动", "预可研"), "预可研/可研启动", 8, 0.82),
    (("government plan", "development plan", "纳入政府规划", "政府规划"), "纳入政府规划", 5, 0.78),
]


def _sentence_for(text: str, keyword: str) -> str:
    parts = re.split(r"(?<=[。！？.!?])\s*|\n+", text)
    keyword_lower = keyword.lower()
    for part in parts:
        if keyword_lower in part.lower():
            cleaned = part.strip()
            return cleaned[:500]
    return text.strip()[:500]


def _match_rule(text: str, rules: list[tuple[tuple[str, ...], str, int, float]]):
    lowered = text.lower()
    for keywords, value, score, confidence in rules:
        for keyword in keywords:
            if keyword.lower() in lowered:
                return value, score, confidence, _sentence_for(text, keyword)
    return None


def extract_facts_deterministic(text: str) -> SourceExtraction:
    facts: list[ExtractedFact] = []

    financing = _match_rule(text, FINANCING_RULES)
    if financing:
        value, score, confidence, quote = financing
        facts.append(
            ExtractedFact(
                field_name="financing",
                value=value,
                score_hint=score,
                evidence_quote=quote,
                confidence=confidence,
            )
        )

    maturity = _match_rule(text, MATURITY_RULES)
    if maturity:
        value, score, confidence, quote = maturity
        facts.append(
            ExtractedFact(
                field_name="project_maturity",
                value=value,
                score_hint=score,
                evidence_quote=quote,
                confidence=confidence,
            )
        )

    if facts:
        dimensions = "、".join(fact.field_name for fact in facts)
        summary = f"识别到可用于重评的经营事实：{dimensions}。"
    else:
        summary = "未识别到满足自动重评阈值的融资或项目成熟度事实，建议人工复核。"

    return SourceExtraction(
        project_detected=bool(facts),
        summary=summary,
        facts=facts,
    )

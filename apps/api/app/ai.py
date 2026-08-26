import json
import re

import httpx

from .config import Settings, get_settings
from .extraction import extract_facts_deterministic
from .models import AnalysisResult, Opportunity, ProjectDiscovery, ProjectParty, SourceExtraction

SOURCE_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "project_detected": {"type": "boolean"},
        "summary": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"field_name": {"type": "string", "enum": ["strategic_fit", "project_maturity", "financing", "client_quality", "capability_fit", "local_position", "competition", "risk_control"]}, "value": {"type": "string"}, "score_hint": {"type": ["integer", "null"]}, "evidence_quote": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}, "required": ["field_name", "value", "score_hint", "evidence_quote", "confidence"]}},
    },
    "required": ["project_detected", "summary", "facts"],
}

PROJECT_PARTY_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "role": {
                "type": "string",
                "enum": ["owner", "financier", "competitor", "partner"],
            },
            "name": {"type": "string"},
            "country": {"type": ["string", "null"]},
            "evidence_quote": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["role", "name", "country", "evidence_quote", "confidence"],
    },
}

PROJECT_DISCOVERY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "project_detected": {"type": "boolean"},
        "title": {"type": "string"},
        "country": {"type": "string"},
        "region": {"type": "string"},
        "sector": {"type": "string"},
        "stage": {"type": "string"},
        "owner": {"type": "string"},
        "estimated_value_usd_m": {"type": ["number", "null"]},
        "summary": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "facts": SOURCE_EXTRACTION_SCHEMA["properties"]["facts"],
        "parties": PROJECT_PARTY_SCHEMA,
    },
    "required": [
        "project_detected",
        "title",
        "country",
        "region",
        "sector",
        "stage",
        "owner",
        "estimated_value_usd_m",
        "summary",
        "confidence",
        "facts",
        "parties",
    ],
}

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "conclusion": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "next_actions": {"type": "array", "items": {"type": "string"}},
        "evidence_gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["conclusion", "strengths", "risks", "next_actions", "evidence_gaps"],
}


def _output_text(payload: dict) -> str:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return content["text"]
    raise ValueError("AI response did not contain output_text")


COUNTRY_TAXONOMY = {
    "nigeria": ("Nigeria", "West Africa"), "尼日利亚": ("尼日利亚", "西非"),
    "ghana": ("Ghana", "West Africa"), "加纳": ("加纳", "西非"),
    "gambia": ("Gambia", "West Africa"), "冈比亚": ("冈比亚", "西非"),
    "senegal": ("Senegal", "West Africa"), "塞内加尔": ("塞内加尔", "西非"),
    "kenya": ("Kenya", "East Africa"), "肯尼亚": ("肯尼亚", "东非"),
    "tanzania": ("Tanzania", "East Africa"), "坦桑尼亚": ("坦桑尼亚", "东非"),
    "uganda": ("Uganda", "East Africa"), "乌干达": ("乌干达", "东非"),
    "ethiopia": ("Ethiopia", "East Africa"), "埃塞俄比亚": ("埃塞俄比亚", "东非"),
    "djibouti": ("Djibouti", "East Africa"), "吉布提": ("吉布提", "东非"),
    "mozambique": ("Mozambique", "Southern Africa"), "莫桑比克": ("莫桑比克", "南部非洲"),
    "angola": ("Angola", "Southern Africa"), "安哥拉": ("安哥拉", "南部非洲"),
    "são tome and príncipe": ("São Tome and Príncipe", "Central Africa"),
    "sao tome and principe": ("São Tome and Príncipe", "Central Africa"),
    "圣多美和普林西比": ("圣多美和普林西比", "中部非洲"),
}

SECTOR_TAXONOMY = [
    (("dredging", "疏浚"), "疏浚工程"),
    (("port", "terminal", "quay", "码头", "港口"), "港口工程"),
    (("bridge", "桥梁"), "桥梁工程"),
    (("rail", "railway", "train express", "铁路", "轨道"), "铁路工程"),
    (("water supply", "water treatment", "pipeline", "pipe and fittings", "供水", "水务", "管线"), "水务工程"),
    (("transmission line", "substation", "kv transmission", "输电", "变电站"), "输变电工程"),
    (("irrigation", "灌溉"), "灌溉工程"),
    (("airport", "机场"), "机场工程"),
    (("road", "highway", "corridor", "route nationale", "feeder roads", "公路", "道路"), "公路工程"),
]


def _contains_taxonomy_term(lowered: str, term: str) -> bool:
    """Match ASCII taxonomy terms as tokens/phrases, not arbitrary substrings.

    This prevents false positives such as matching ``port`` inside ``report`` while retaining
    substring matching for Chinese terms where word boundaries are not represented by spaces.
    """
    if not term.isascii():
        return term in lowered
    return re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", lowered) is not None


def _party_from_patterns(
    text: str,
    *,
    role: str,
    patterns: list[str],
    country: str | None,
) -> ProjectParty | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        name = " ".join(match.group(1).strip().split())
        if len(name) < 2:
            continue
        return ProjectParty(
            role=role,
            name=name[:320],
            country=country,
            evidence_quote=" ".join(match.group(0).strip().split())[:1000],
            confidence=0.84,
        )
    return None


def _deterministic_project(text: str, page_title: str) -> ProjectDiscovery:
    lowered = text.lower()
    project_terms = (
        "project", "corridor", "port", "road", "bridge", "highway", "railway", "airport",
        "terminal", "dredging", "water supply", "transmission line", "substation", "irrigation",
        "工程", "项目", "公路", "港口", "桥梁", "铁路", "机场", "疏浚", "供水", "输电", "灌溉",
    )
    detected = any(_contains_taxonomy_term(lowered, term) for term in project_terms)

    country, region = "待识别", "待识别"
    for keyword, values in COUNTRY_TAXONOMY.items():
        if keyword in lowered:
            country, region = values
            break

    sector = "待识别"
    for terms, label in SECTOR_TAXONOMY:
        if any(_contains_taxonomy_term(lowered, term) for term in terms):
            sector = label
            break

    extracted = extract_facts_deterministic(text)
    stage = "待核实"
    maturity = next((fact for fact in extracted.facts if fact.field_name == "project_maturity"), None)
    if maturity:
        stage = maturity.value

    value = None
    value_match = re.search(r"(?:US\$|USD\s*|\$)\s*([0-9]+(?:\.[0-9]+)?)\s*(million|billion|m|bn)?", text, re.I)
    if value_match:
        raw = float(value_match.group(1))
        unit = (value_match.group(2) or "").lower()
        value = raw * 1000 if unit in {"billion", "bn"} else raw

    known_country = country if country != "待识别" else None
    owner_party = _party_from_patterns(
        text,
        role="owner",
        country=known_country,
        patterns=[
            r"(?:owner|employer|client|业主)[：:\s]+([^\n。.;]{3,120})",
            r"(?:executing agency|implementing agency)[：:\s]+([^\n。.;]{3,120})",
        ],
    )
    owner = owner_party.name if owner_party else "待识别"

    parties: list[ProjectParty] = []
    if owner_party:
        parties.append(owner_party)
    for role, patterns in (
        (
            "financier",
            [
                r"(?:financier|lender|financing institution|融资方|贷款方)[：:\s]+([^\n。.;]{3,120})",
                r"(?:financed|funded)\s+by[：:\s]+([^\n。.;]{3,120})",
            ],
        ),
        (
            "competitor",
            [
                r"(?:competitor|竞争对手)[：:\s]+([^\n。.;]{3,120})",
                r"(?:preferred bidder|selected bidder|中标候选人)[：:\s]+([^\n。.;]{3,120})",
            ],
        ),
        (
            "partner",
            [
                r"(?:joint venture with|consortium with|partner(?:ed)? with)[：:\s]+([^\n。.;]{3,120})",
                r"(?:合作方|联合体成员)[：:\s]+([^\n。.;]{3,120})",
            ],
        ),
    ):
        party = _party_from_patterns(
            text,
            role=role,
            patterns=patterns,
            country=known_country,
        )
        if party and all(
            not (existing.role == party.role and existing.name.casefold() == party.name.casefold())
            for existing in parties
        ):
            parties.append(party)

    title = page_title.strip() if page_title and page_title != "公开来源" else "待确认工程项目机会"
    confidence = 0.62 if detected else 0.25
    if country != "待识别": confidence += 0.08
    if sector != "待识别": confidence += 0.08
    if extracted.facts: confidence += 0.08
    confidence = min(confidence, 0.88)
    return ProjectDiscovery(
        project_detected=detected,
        title=title[:300],
        country=country,
        region=region,
        sector=sector,
        stage=stage,
        owner=owner,
        estimated_value_usd_m=value,
        summary=("公开来源中识别到工程项目机会，已形成待人工确认的初步项目画像。" if detected else "未从当前文本识别出足够明确的工程项目机会。"),
        confidence=confidence,
        facts=extracted.facts,
        parties=parties,
    )


class AIService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.ai_enabled

    async def _structured_response(self, *, model: str, instructions: str, user_input: str, schema_name: str, schema: dict) -> dict:
        if not self.settings.ai_api_key:
            raise RuntimeError("AI_API_KEY is not configured")
        url = f"{self.settings.ai_base_url.rstrip('/')}/responses"
        body = {"model": model, "instructions": instructions, "input": user_input, "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}}}
        headers = {"Authorization": f"Bearer {self.settings.ai_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            return json.loads(_output_text(response.json()))

    async def extract_source(self, text: str, use_ai: bool = True) -> tuple[SourceExtraction, str]:
        if use_ai and self.enabled:
            try:
                data = await self._structured_response(model=self.settings.ai_model_extraction, instructions="你是海外工程市场情报分析器。只抽取文本中有明确证据支持的事实。score_hint 只能映射到既定100分评分维度，不确定时返回 null；不得创造人物、金额、融资状态或项目阶段。evidence_quote 应是支撑事实的最短原文片段。", user_input=text, schema_name="zhituo_source_extraction", schema=SOURCE_EXTRACTION_SCHEMA)
                return SourceExtraction.model_validate(data), "ai"
            except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError):
                pass
        return extract_facts_deterministic(text), "deterministic"

    async def discover_project(self, text: str, *, page_title: str = "公开来源", use_ai: bool = True) -> tuple[ProjectDiscovery, str]:
        if use_ai and self.enabled:
            try:
                data = await self._structured_response(
                    model=self.settings.ai_model_extraction,
                    instructions=(
                        "你是海外工程市场机会发现智能体。判断文本是否描述具体或潜在基础设施工程项目。"
                        "只填写原文可支持的项目名称、国别、区域、专业、阶段、业主和金额；无法确认时写‘待识别/待核实’。"
                        "parties 只提取原文明确出现的 owner、financier、competitor、partner，必须提供最短证据原文；"
                        "不要根据常识猜测融资方、竞争对手、合作伙伴或企业关系。"
                        "不要把宏观政策、无具体项目的行业新闻误报成项目。facts 仅记录能映射到既定评分维度且有原文证据的事实。"
                    ),
                    user_input=f"网页标题：{page_title}\n\n正文：\n{text}",
                    schema_name="zhituo_project_discovery",
                    schema=PROJECT_DISCOVERY_SCHEMA,
                )
                return ProjectDiscovery.model_validate(data), "ai"
            except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError):
                pass
        return _deterministic_project(text, page_title), "deterministic"

    async def analyze(self, opportunity: Opportunity) -> tuple[AnalysisResult, str]:
        if self.enabled:
            try:
                data = await self._structured_response(model=self.settings.ai_model_analysis, instructions="你是海外工程市场经营参谋。基于给定结构化项目数据和证据形成简洁经营研判。不得声称精确中标概率，不得补造关系或未提供的事实。证据不足必须明确列入 evidence_gaps。", user_input=opportunity.model_dump_json(indent=2), schema_name="zhituo_opportunity_analysis", schema=ANALYSIS_SCHEMA)
                return AnalysisResult.model_validate(data), "ai"
            except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError):
                pass
        evidence_gaps: list[str] = []
        if not opportunity.evidence:
            evidence_gaps.append("当前项目尚未绑定高质量证据来源")
        if opportunity.confidence < 70:
            evidence_gaps.append("研判置信度偏低，需要补充关键事实")
        return AnalysisResult(conclusion=opportunity.pursuit_thesis, strengths=[f"当前机会评分 {opportunity.score} / {opportunity.grade} 级"], risks=["规则评分不能替代经营负责人最终决策"], next_actions=opportunity.next_actions, evidence_gaps=evidence_gaps), "deterministic"

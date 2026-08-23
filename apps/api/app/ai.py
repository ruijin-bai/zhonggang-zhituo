import json

import httpx

from .config import Settings, get_settings
from .extraction import extract_facts_deterministic
from .models import AnalysisResult, Opportunity, SourceExtraction


SOURCE_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "project_detected": {"type": "boolean"},
        "summary": {"type": "string"},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "field_name": {
                        "type": "string",
                        "enum": [
                            "strategic_fit",
                            "project_maturity",
                            "financing",
                            "client_quality",
                            "capability_fit",
                            "local_position",
                            "competition",
                            "risk_control",
                        ],
                    },
                    "value": {"type": "string"},
                    "score_hint": {"type": ["integer", "null"]},
                    "evidence_quote": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["field_name", "value", "score_hint", "evidence_quote", "confidence"],
            },
        },
    },
    "required": ["project_detected", "summary", "facts"],
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


class AIService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def _structured_response(
        self,
        *,
        model: str,
        instructions: str,
        user_input: str,
        schema_name: str,
        schema: dict,
    ) -> dict:
        if not self.settings.ai_api_key or not model:
            raise RuntimeError("AI provider or model is not configured")
        url = f"{self.settings.ai_base_url.rstrip('/')}/responses"
        body = {
            "model": model,
            "instructions": instructions,
            "input": user_input,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self.settings.ai_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.settings.ai_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            return json.loads(_output_text(response.json()))

    async def extract_source(self, text: str, use_ai: bool = True) -> tuple[SourceExtraction, str]:
        if use_ai and self.settings.ai_extraction_enabled:
            try:
                data = await self._structured_response(
                    model=self.settings.ai_model_extraction,
                    instructions=(
                        "你是海外工程市场情报分析器。只抽取来源文本中有明确证据支持的事实。"
                        "score_hint 只能映射到既定100分评分维度，不确定时必须返回 null；"
                        "不得创造人物、金额、融资状态或项目阶段。evidence_quote 应是支撑事实的最短原文片段。"
                    ),
                    user_input=text,
                    schema_name="zhituo_source_extraction",
                    schema=SOURCE_EXTRACTION_SCHEMA,
                )
                return SourceExtraction.model_validate(data), "ai"
            except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError):
                pass
        return extract_facts_deterministic(text), "deterministic"

    async def analyze(self, opportunity: Opportunity) -> tuple[AnalysisResult, str]:
        if self.settings.ai_analysis_enabled:
            try:
                context = opportunity.model_dump_json(indent=2)
                data = await self._structured_response(
                    model=self.settings.ai_model_analysis,
                    instructions=(
                        "你是海外工程市场经营参谋。基于给定结构化项目数据和证据形成简洁经营研判。"
                        "不得声称精确中标概率，不得补造关系或未提供的事实。证据不足必须明确列入 evidence_gaps。"
                    ),
                    user_input=context,
                    schema_name="zhituo_opportunity_analysis",
                    schema=ANALYSIS_SCHEMA,
                )
                return AnalysisResult.model_validate(data), "ai"
            except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError):
                pass

        evidence_gaps: list[str] = []
        if not opportunity.evidence:
            evidence_gaps.append("当前项目尚未绑定高质量证据来源")
        if opportunity.confidence < 70:
            evidence_gaps.append("研判置信度偏低，需要补充关键事实")
        result = AnalysisResult(
            conclusion=opportunity.pursuit_thesis,
            strengths=[f"当前机会评分 {opportunity.score} / {opportunity.grade} 级"],
            risks=["规则评分不能替代经营负责人最终决策"],
            next_actions=opportunity.next_actions,
            evidence_gaps=evidence_gaps,
        )
        return result, "deterministic"

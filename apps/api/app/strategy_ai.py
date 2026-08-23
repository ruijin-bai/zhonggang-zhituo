import json

import httpx
from pydantic import BaseModel, Field

from .ai import AIService
from .models import Opportunity


class StrategyDraft(BaseModel):
    win_theme: str
    client_need: str
    differentiation: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next_moves: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class RedTeamChallenge(BaseModel):
    verdict: str
    failure_modes: list[str] = Field(default_factory=list)
    weak_assumptions: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    counter_moves: list[str] = Field(default_factory=list)


STRATEGY_SCHEMA = {"type":"object","additionalProperties":False,"properties":{"win_theme":{"type":"string"},"client_need":{"type":"string"},"differentiation":{"type":"array","items":{"type":"string"}},"gaps":{"type":"array","items":{"type":"string"}},"next_moves":{"type":"array","items":{"type":"string"}},"assumptions":{"type":"array","items":{"type":"string"}}},"required":["win_theme","client_need","differentiation","gaps","next_moves","assumptions"]}
RED_TEAM_SCHEMA = {"type":"object","additionalProperties":False,"properties":{"verdict":{"type":"string"},"failure_modes":{"type":"array","items":{"type":"string"}},"weak_assumptions":{"type":"array","items":{"type":"string"}},"missing_evidence":{"type":"array","items":{"type":"string"}},"counter_moves":{"type":"array","items":{"type":"string"}}},"required":["verdict","failure_modes","weak_assumptions","missing_evidence","counter_moves"]}


def deterministic_draft(opportunity: Opportunity) -> StrategyDraft:
    gaps = []
    if opportunity.confidence < 70: gaps.append("关键事实置信度不足，先补融资、采购与业主决策信息")
    if not opportunity.evidence: gaps.append("缺少可追溯高质量证据")
    return StrategyDraft(win_theme=opportunity.pursuit_thesis, client_need=opportunity.summary, differentiation=["围绕项目需求匹配可验证的同类工程履约能力", "结合属地资源与供应链形成可落地交付方案"], gaps=gaps or ["竞争格局与客户决策链仍需补充"], next_moves=opportunity.next_actions, assumptions=["差异化优势需由项目业绩和来源证据进一步验证"])


def deterministic_red_team(opportunity: Opportunity, strategy: dict) -> RedTeamChallenge:
    missing = []
    if not strategy.get("competitors"): missing.append("没有竞争对手证据，无法判断相对优势")
    if not strategy.get("stakeholders"): missing.append("客户决策链为空，经营触点存在盲区")
    if opportunity.confidence < 70: missing.append("基础机会研判置信度不足")
    return RedTeamChallenge(verdict="当前策略可作为经营假设，但尚不足以证明可赢。", failure_modes=["把公司通用能力误当成针对本项目的差异化优势", "项目窗口或采购路径变化导致经营动作失焦"], weak_assumptions=["客户真实优先级可能与当前公开信息不一致"], missing_evidence=missing, counter_moves=["用一手或高等级来源核实采购窗口和决策标准", "逐项为赢标主张绑定可验证业绩与客户价值"])


async def generate_strategy(opportunity: Opportunity) -> tuple[StrategyDraft, str]:
    service = AIService()
    if service.enabled:
        try:
            data = await service._structured_response(model=service.settings.ai_model_analysis, instructions="你是国际工程市场经营策略顾问。根据机会数据生成Pursuit Strategy初稿。严格区分事实与假设，不得创造竞争对手、关键人、关系、报价或客户态度。差异化必须表达客户价值；证据不足写入gaps或assumptions。", user_input=opportunity.model_dump_json(indent=2), schema_name="zhituo_strategy_draft", schema=STRATEGY_SCHEMA)
            return StrategyDraft.model_validate(data), "ai"
        except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError): pass
    return deterministic_draft(opportunity), "deterministic"


async def red_team(opportunity: Opportunity, strategy: dict) -> tuple[RedTeamChallenge, str]:
    service = AIService()
    if service.enabled:
        try:
            data = await service._structured_response(model=service.settings.ai_model_analysis, instructions="你是国际工程投标经营红队。目标不是润色，而是找出为什么这套策略可能拿不到项目。只依据提供的数据，识别失败路径、脆弱假设、缺失证据并提出反制动作；禁止虚构竞争对手、关键人、关系和报价。", user_input=json.dumps({"opportunity":opportunity.model_dump(mode="json"),"strategy":strategy}, ensure_ascii=False, indent=2), schema_name="zhituo_strategy_red_team", schema=RED_TEAM_SCHEMA)
            return RedTeamChallenge.model_validate(data), "ai"
        except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError): pass
    return deterministic_red_team(opportunity, strategy), "deterministic"

import { demoOpportunities } from "./demo";

export const HERO_ID = "west-africa-port-access-corridor";

export function getDemoHero() {
  return demoOpportunities.find((item) => item.id === HERO_ID) ?? demoOpportunities[0];
}

export function getDemoStrategyWorkspace() {
  const opportunity = getDemoHero();
  return {
    opportunity,
    readiness: 75,
    readiness_label: "策略基本成形",
    evidence_warnings: ["采购评价权重尚无正式证据", "融资方对实施方案的核心约束待核实"],
    strategy: {
      win_theme: "以港口—疏港交通一体化交付能力，帮助业主降低多接口协调风险并提升项目落地确定性。",
      client_need: "在融资与采购尚处前期时，尽快形成可融资、可采购、可实施的一体化建设路径。",
      differentiation: [
        "港航+道路交通跨专业一体化组织能力",
        "海外属地供应链和施工资源可支撑快速落地",
        "同类大型基础设施履约经验可降低接口与工期风险",
      ],
      gaps: ["采购评价权重尚无正式证据", "融资方对实施方案的核心约束待核实"],
      competitors: [],
      stakeholders: [
        {
          name: "业主项目执行机构",
          organization: "项目业主",
          role: "项目决策与采购组织",
          influence: "high",
          stance: "unknown",
          evidence: "公开项目组织信息，具体人员待核实",
          confidence: 65,
        },
        {
          name: "融资机构项目团队",
          organization: "融资方",
          role: "融资条件与项目可实施性审查",
          influence: "high",
          stance: "unknown",
          evidence: "具体机构要求待正式来源确认",
          confidence: 55,
        },
      ],
      next_moves: [
        "核实采购模式与预计招标时间",
        "形成港口+疏港交通一体化方案摘要",
        "获取融资约束与采购评价标准的一手信息",
      ],
    },
  };
}

export function getDemoTrackingBoard() {
  const opportunity = getDemoHero();
  return {
    watch_count: 1,
    open_action_count: 3,
    overdue_action_count: 0,
    open_alert_count: 2,
    items: [
      {
        opportunity,
        watch: {
          priority: "high",
          owner: "市场经营负责人",
          next_review_at: "2026-08-30T09:00:00+00:00",
        },
        actions: [
          { id: 1, title: "核实采购模式与预计招标时间", owner: "市场经理", priority: "high", status: "open", due_at: "2026-08-28T09:00:00+00:00" },
          { id: 2, title: "梳理业主与融资方决策链", owner: "区域团队", priority: "high", status: "open", due_at: "2026-08-31T09:00:00+00:00" },
          { id: 3, title: "形成港口+疏港交通一体化方案摘要", owner: "技术经营组", priority: "high", status: "open", due_at: "2026-09-02T09:00:00+00:00" },
        ],
        alerts: [
          { id: 1, severity: "warning", title: "采购评价权重待核实", message: "当前缺少正式采购评价标准，不宜将内部判断作为既定规则。" },
          { id: 2, severity: "info", title: "融资实施约束待补充", message: "建议获取融资方对采购和实施安排的一手要求。" },
        ],
        timeline: [
          { type: "strategy_updated", at: "2026-08-23T09:00:00+00:00" },
          { type: "watch_started", at: "2026-08-23T08:30:00+00:00" },
        ],
      },
    ],
  };
}

export function getDemoBattlecard() {
  const opportunity = getDemoHero();
  const workspace = getDemoStrategyWorkspace();
  const board = getDemoTrackingBoard();
  return {
    opportunity,
    card: {
      decision_line: "建议重点跟踪，但关键采购与融资约束仍需一手证据确认。",
      generated_at: "2026-08-23T12:00:00+00:00",
      versions: [{ version: 2 }],
      strategy: { ...workspace.strategy, readiness: workspace.readiness },
      execution: {
        owner: "市场经营负责人",
        priority: "high",
        actions: board.items[0].actions,
        alerts: board.items[0].alerts,
      },
    },
  };
}

export const demoRedTeam = {
  mode: "offline-fallback",
  challenge: {
    verdict: "当前策略方向可用，但还不足以证明项目具备确定性优势。",
    failure_modes: [
      "采购评价权重未知，现有差异化优势可能并非业主真正关注项",
      "融资方实施约束未核实，技术经营方案可能与融资条件存在偏差",
      "竞争格局证据不足，无法确认一体化交付能力是否构成真实差异化",
    ],
    missing_evidence: ["正式采购评价标准", "融资方关键实施约束", "主要竞争方公开业绩与参与迹象"],
    counter_moves: ["获取采购文件或顾问口径", "核实融资条件和采购边界", "建立只基于公开证据的竞争对手画像"],
  },
};

export const demoStrategyDraft = {
  mode: "offline-fallback",
  draft: {
    ...getDemoStrategyWorkspace().strategy,
    assumptions: ["采购模式仍待正式来源确认", "竞争格局尚未形成充分证据"],
  },
};

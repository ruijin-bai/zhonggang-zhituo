import type { Opportunity } from "./types";

export const demoOpportunities: Opportunity[] = [
  {
    id: "west-africa-port-access-corridor",
    title: "西非港口集疏运走廊示范项目",
    country: "尼日利亚",
    region: "西非",
    sector: "港口连接公路",
    stage: "融资与采购准备中",
    owner: "示范业主机构",
    estimated_value_usd_m: 320,
    summary: "用于工程化验证的脱敏示范机会。系统展示融资证据进入后，机会评分从 B 级提升至 A 级的完整链路。",
    score: 81,
    grade: "A",
    confidence: 86,
    decision: "GO",
    breakdown: { strategic_fit: 18, project_maturity: 13, financing: 15, client_quality: 8, capability_fit: 13, local_position: 7, competition: 4, risk_control: 3 },
    evidence: [
      { id: "ev-1", rank: "S", title: "融资批准示范公告", publisher: "多边金融机构（示范）", published_at: "2026-08-23", fact: "项目融资由‘谈判明确’更新为‘已获批’，融资确定性显著提升。" },
      { id: "ev-2", rank: "S", title: "采购计划示范文件", publisher: "业主机构（示范）", published_at: "2026-08-23", fact: "业主已进入采购准备阶段，项目成熟度提升。" }
    ],
    score_history: [
      { date: "2026-08-20", total: 72, grade: "B", note: "融资尚处于谈判阶段，采购计划未明确。" },
      { date: "2026-08-23", total: 81, grade: "A", note: "新增高等级融资与采购证据，融资 +7、成熟度 +2。" }
    ],
    pursuit_thesis: "项目与港航及交通基础设施能力匹配，属地区域基础较好；现阶段核心是抓住融资落地后的早期采购窗口，以业绩与属地资源形成进入优势。",
    next_actions: ["核实采购模式与时间表", "梳理业主与融资方决策链", "建立潜在竞争对手清单", "准备同类业绩与属地资源证明"],
    is_demo: true
  },
  {
    id: "east-africa-port-expansion",
    title: "东非港区扩建机会",
    country: "肯尼亚",
    region: "东非",
    sector: "港口工程",
    stage: "可研完成",
    owner: "示范港务机构",
    estimated_value_usd_m: 210,
    summary: "需求清晰，但融资仍需进一步验证。",
    score: 74,
    grade: "B",
    confidence: 71,
    decision: "WATCH",
    breakdown: { strategic_fit: 17, project_maturity: 10, financing: 8, client_quality: 8, capability_fit: 14, local_position: 6, competition: 7, risk_control: 4 },
    evidence: [], score_history: [{ date: "2026-08-22", total: 74, grade: "B", note: "初始研判。" }],
    pursuit_thesis: "专业匹配较高，但融资来源尚未形成充分证据。", next_actions: ["确认融资来源", "跟踪采购顾问动态"], is_demo: true
  },
  {
    id: "west-africa-urban-bridge",
    title: "西非城市跨河桥梁机会",
    country: "加纳",
    region: "西非",
    sector: "桥梁工程",
    stage: "政府规划",
    owner: "示范交通主管机构",
    estimated_value_usd_m: 145,
    summary: "战略方向匹配，但项目尚处早期。",
    score: 61,
    grade: "C",
    confidence: 63,
    decision: "CAUTION",
    breakdown: { strategic_fit: 15, project_maturity: 5, financing: 5, client_quality: 7, capability_fit: 13, local_position: 5, competition: 7, risk_control: 4 },
    evidence: [], score_history: [{ date: "2026-08-21", total: 61, grade: "C", note: "项目成熟度偏低。" }],
    pursuit_thesis: "适合低成本跟踪，不宜过早投入大量经营资源。", next_actions: ["跟踪可研启动", "确认预算来源"], is_demo: true
  }
];

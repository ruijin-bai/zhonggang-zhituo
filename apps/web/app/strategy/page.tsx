import Link from "next/link";
import StrategyLab from "./StrategyLab";
import { getOpportunities } from "@/lib/api";
import { serverApiFetch } from "@/lib/server-api";
import { DEMO_FALLBACK_ALLOWED, getDemoStrategyWorkspace, withDemoFlag } from "@/lib/demo-operating";
import DemoDataBanner from "@/components/DemoDataBanner";

type Opportunity = {
  id: string;
  title: string;
  country: string;
  sector: string;
  stage: string;
  score: number;
  grade: string;
  confidence: number;
  pursuit_thesis: string;
  summary: string;
  next_actions: string[];
};

type Competitor = {
  name: string;
  position?: string;
  confidence?: number;
  evidence?: string;
};

type Stakeholder = {
  name: string;
  organization: string;
  role: string;
  influence?: string;
  stance?: string;
  confidence?: number;
};

type Strategy = {
  win_theme?: string;
  client_need?: string;
  differentiation?: string[];
  competitors?: Competitor[];
  stakeholders?: Stakeholder[];
  gaps?: string[];
  next_moves?: string[];
};

type Workspace = {
  readiness?: number;
  readiness_label?: string;
  evidence_warnings?: string[];
  strategy?: Strategy;
  isDemo?: boolean;
};

const INFLUENCE_LABEL: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
  unknown: "未知",
};

const STANCE_LABEL: Record<string, string> = {
  supportive: "支持",
  neutral: "中立",
  opposing: "反对",
  unknown: "未知",
};

function influenceLabel(value?: string) {
  return INFLUENCE_LABEL[value ?? ""] ?? "未知";
}

function stanceLabel(value?: string) {
  return STANCE_LABEL[value ?? ""] ?? "未知";
}

async function getStrategy(id: string): Promise<Workspace | null> {
  try {
    const response = await serverApiFetch(`/api/opportunities/${encodeURIComponent(id)}/strategy`, {
      cache: "no-store",
    });
    if (response.ok) return await response.json();
    throw new Error(`HTTP ${response.status}`);
  } catch (error) {
    if (!DEMO_FALLBACK_ALLOWED) throw error;
    const demo = getDemoStrategyWorkspace();
    return demo.opportunity.id === id ? withDemoFlag(demo) : null;
  }
}

export default async function StrategyPage({
  searchParams,
}: {
  searchParams: Promise<{ id?: string }>;
}) {
  const params = await searchParams;
  const opportunities = (await getOpportunities()) as Opportunity[];
  const selected = opportunities.find((item) => item.id === params.id) ?? opportunities[0];
  const workspace = selected ? await getStrategy(selected.id) : null;
  const strategy = workspace?.strategy;
  const gaps = strategy?.gaps?.length ? strategy.gaps : (workspace?.evidence_warnings ?? []);
  const nextMoves = strategy?.next_moves?.length ? strategy.next_moves : selected?.next_actions ?? [];

  return (
    <>
      {workspace?.isDemo ? <DemoDataBanner scope="赢标经营策略" /> : null}

      <div className="page-head">
        <div>
          <div className="eyebrow">怎么拿</div>
          <h1>赢标经营策略</h1>
          <p className="muted">从机会判断进入经营攻坚：形成策略、主动证伪、再转化为战役行动。</p>
        </div>
      </div>

      <div className="strategy-tabs">
        {opportunities.slice(0, 6).map((item) => (
          <Link
            key={item.id}
            className={selected?.id === item.id ? "strategy-tab active" : "strategy-tab"}
            href={`/strategy?id=${item.id}`}
          >
            {item.title}
          </Link>
        ))}
      </div>

      {!selected ? (
        <div className="section">暂无正式机会。</div>
      ) : (
        <>
          <section className="section strategy-hero">
            <div>
              <span className="eyebrow">
                {selected.country} · {selected.sector}
              </span>
              <h2>{selected.title}</h2>
              <p>{selected.stage}</p>
            </div>
            <div>
              <span>机会评分</span>
              <strong>
                {selected.score}/{selected.grade}
              </strong>
            </div>
            <div>
              <span>策略成熟度</span>
              <strong>{workspace?.readiness ?? 0}%</strong>
              <small>{workspace?.readiness_label ?? "待建立"}</small>
            </div>
          </section>

          <StrategyLab id={selected.id} />

          <div className="grid-2 strategy-grid">
            <div className="stack">
              <section className="section">
                <h2>赢标主张</h2>
                <p className="strategy-statement">{strategy?.win_theme || selected.pursuit_thesis}</p>
                <div className="policy-note">必须回答客户为什么选我们，而不是重复公司能力。</div>
              </section>

              <section className="section">
                <h2>客户核心诉求</h2>
                <p>{strategy?.client_need || selected.summary}</p>
              </section>

              <section className="section">
                <h2>差异化优势</h2>
                {strategy?.differentiation?.length ? (
                  <ul className="action-list">
                    {strategy.differentiation.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">尚未形成证据化差异优势。</p>
                )}
              </section>

              <section className="section">
                <h2>竞争格局</h2>
                {strategy?.competitors?.length ? (
                  strategy.competitors.map((item) => (
                    <div className="strategy-entity" key={item.name}>
                      <strong>{item.name}</strong>
                      <span>
                        {item.position} · 置信度 {item.confidence}%
                      </span>
                      <p>{item.evidence || "证据待补"}</p>
                    </div>
                  ))
                ) : (
                  <p className="muted">尚未建立竞争对手画像，不在缺乏证据时推测对手报价或关系。</p>
                )}
              </section>
            </div>

            <div className="stack">
              <section className="section">
                <h2>策略缺口</h2>
                <ul className="action-list">
                  {gaps.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>

              <section className="section">
                <h2>客户决策链</h2>
                {strategy?.stakeholders?.length ? (
                  strategy.stakeholders.map((item) => (
                    <div className="strategy-entity" key={`${item.organization}-${item.name}`}>
                      <strong>{item.name}</strong>
                      <span>
                        {item.organization} · {item.role}
                      </span>
                      <p>
                        影响力 {influenceLabel(item.influence)} · 态度 {stanceLabel(item.stance)} ·
                        置信度 {item.confidence}%
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="muted">暂无经证据核实的关键人。</p>
                )}
              </section>

              <section className="section">
                <h2>下一轮经营战役</h2>
                <ol className="action-list">
                  {nextMoves.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ol>
              </section>

              <section className="section">
                <h2>证据纪律</h2>
                <p className="muted">
                  允许“未知”，不允许把猜测包装成事实。竞争关系、客户态度、关键人影响力均应保留来源和置信度。
                </p>
              </section>
            </div>
          </div>
        </>
      )}
    </>
  );
}

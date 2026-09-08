import Link from "next/link";
import PrintButton from "./PrintButton";
import { getOpportunities } from "@/lib/api";
import { serverApiFetch } from "@/lib/server-api";
import { DEMO_FALLBACK_ALLOWED, getDemoBattlecard, withDemoFlag } from "@/lib/demo-operating";
import DemoDataBanner from "@/components/DemoDataBanner";

type Opportunity = {
  id: string;
  title: string;
  country: string;
  sector: string;
  stage: string;
  owner: string;
  score: number;
  grade: string;
  decision: string;
  confidence: number;
  pursuit_thesis: string;
  estimated_value_usd_m?: number | null;
};

type Action = {
  title: string;
  owner?: string;
  priority?: string;
  due_at?: string | null;
};

type Alert = { title: string };

type BattlecardStrategy = {
  readiness?: number;
  win_theme?: string;
  client_need?: string;
  differentiation?: string[];
  gaps?: string[];
  stakeholders?: { name: string }[];
  competitors?: { name: string }[];
};

type BattlecardPayload = {
  decision_line: string;
  generated_at: string;
  versions?: { version: number }[];
  strategy: BattlecardStrategy;
  execution: {
    owner?: string;
    priority?: string;
    actions?: Action[];
    alerts?: Alert[];
  };
  isDemo?: boolean;
};

type Loaded = {
  opportunities: Opportunity[];
  opportunity: Opportunity;
  card: BattlecardPayload;
};

function priorityLabel(value?: string) {
  if (value === "high") return "高优先级";
  if (value === "medium") return "中优先级";
  if (value === "low") return "低优先级";
  return value ?? "未设置";
}

function valueLabel(value?: number | null) {
  return value ? `$${value}m` : "待核实";
}

async function load(id?: string): Promise<Loaded | null> {
  const opportunities = (await getOpportunities()) as Opportunity[];
  const opportunity = opportunities.find((item) => item.id === id) ?? opportunities[0];
  if (!opportunity) return null;

  try {
    const response = await serverApiFetch(
      `/api/opportunities/${encodeURIComponent(opportunity.id)}/battlecard`,
      { cache: "no-store" },
    );
    if (!response.ok) throw new Error("battlecard unavailable");
    const card = (await response.json()) as BattlecardPayload;
    return { opportunities, opportunity, card };
  } catch (error) {
    if (!DEMO_FALLBACK_ALLOWED) throw error;
    const demo = getDemoBattlecard();
    if (opportunity.id !== demo.opportunity.id) return null;
    return { opportunities, opportunity, card: withDemoFlag(demo.card) as BattlecardPayload };
  }
}

export default async function Battlecard({
  searchParams,
}: {
  searchParams: Promise<{ id?: string }>;
}) {
  const params = await searchParams;
  const data = await load(params.id);

  if (!data) {
    return (
      <div className="empty-state">
        <h2>暂无作战卡数据</h2>
        <p>请先初始化 Demo 数据或将项目加入正式机会池。</p>
        <Link href="/opportunities">返回机会池 →</Link>
      </div>
    );
  }

  const { opportunities, opportunity: o, card: c } = data;
  const strategy = c.strategy ?? {};
  const execution = c.execution ?? {};
  const actions = execution.actions ?? [];
  const alerts = execution.alerts ?? [];
  const differentiation = strategy.differentiation ?? [];
  const gaps = strategy.gaps ?? [];
  const stakeholders = strategy.stakeholders ?? [];
  const competitors = strategy.competitors ?? [];
  const hasRisk = gaps.length > 0 || alerts.length > 0;

  return (
    <>
      {c.isDemo ? <DemoDataBanner scope="一页式经营作战卡" /> : null}

      <div className="page-head no-print">
        <div>
          <div className="eyebrow">一页式经营决策</div>
          <h1>一页式经营作战卡</h1>
          <p className="muted">领导一页看清：值不值得追、凭什么拿、可能输在哪、下一步谁来做。</p>
        </div>
        <PrintButton />
      </div>

      <div className="strategy-tabs no-print">
        {opportunities.slice(0, 6).map((item) => (
          <Link
            key={item.id}
            className={o.id === item.id ? "strategy-tab active" : "strategy-tab"}
            href={`/battlecard?id=${item.id}`}
          >
            {item.title}
          </Link>
        ))}
      </div>

      <article className="battlecard">
        <header className="battle-head">
          <div>
            <div className="eyebrow">中港智拓 · 经营作战卡</div>
            <h1>{o.title}</h1>
            <p>
              {o.country} · {o.sector} · {o.stage} · {o.owner}
            </p>
          </div>
          <div className="battle-decision">
            <strong>{o.decision}</strong>
            <span>
              {o.score}分 / {o.grade}级
            </span>
            <small>策略成熟度 {strategy.readiness ?? 0}%</small>
          </div>
        </header>

        <div className="battle-strip">
          <b>{c.decision_line}</b>
          <span>负责人：{execution.owner ?? "未指定"}</span>
          <span>优先级：{priorityLabel(execution.priority)}</span>
        </div>

        <div className="battle-grid">
          <section>
            <h2>01｜为什么值得追</h2>
            <p>{o.pursuit_thesis}</p>
            <div className="battle-metrics">
              <span>
                置信度 <b>{o.confidence}%</b>
              </span>
              <span>
                项目规模 <b>{valueLabel(o.estimated_value_usd_m)}</b>
              </span>
            </div>
          </section>

          <section>
            <h2>02｜赢标主张</h2>
            <p className="strategy-statement">{strategy.win_theme}</p>
            <small>{strategy.client_need}</small>
          </section>

          <section>
            <h2>03｜凭什么拿</h2>
            {differentiation.length ? (
              <ul>
                {differentiation.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">差异化优势待证据化。</p>
            )}
          </section>

          <section>
            <h2>04｜可能输在哪</h2>
            {hasRisk ? (
              <ul>
                {gaps.map((item) => (
                  <li key={item}>{item}</li>
                ))}
                {alerts.map((item) => (
                  <li key={item.title}>{item.title}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">当前无已识别关键缺口。</p>
            )}
          </section>

          <section>
            <h2>05｜客户与竞争</h2>
            <p>
              <b>关键人：</b>
              {stakeholders.length ? stakeholders.map((item) => item.name).join("、") : "决策链待核实"}
            </p>
            <p>
              <b>竞争：</b>
              {competitors.length ? competitors.map((item) => item.name).join("、") : "竞争格局待核实"}
            </p>
          </section>

          <section>
            <h2>06｜下一轮战役</h2>
            {actions.length ? (
              <ol>
                {actions.map((item) => (
                  <li key={item.title}>
                    <b>{item.title}</b>
                    <br />
                    <small>
                      {item.owner} · {priorityLabel(item.priority)}
                      {item.due_at ? ` · ${item.due_at.slice(0, 10)}` : ""}
                    </small>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">尚未创建经营行动。</p>
            )}
          </section>
        </div>

        <footer className="battle-foot">
          <span>策略版本：{c.versions?.length ? `V${c.versions[0].version}` : "V0"}</span>
          <span>生成时间：{c.generated_at?.slice(0, 16).replace("T", " ")} UTC</span>
          <span>AI辅助研判，不替代经营决策</span>
        </footer>
      </article>
    </>
  );
}

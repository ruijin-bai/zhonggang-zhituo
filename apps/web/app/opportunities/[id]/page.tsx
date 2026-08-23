import { notFound } from "next/navigation";
import { getOpportunity } from "@/lib/api";
import type { ScoreBreakdown } from "@/lib/types";

const scoreMeta: Array<[keyof ScoreBreakdown, string, number]> = [
  ["strategic_fit", "战略匹配度", 20], ["project_maturity", "项目成熟度", 15], ["financing", "融资确定性", 15], ["client_quality", "业主与决策质量", 10],
  ["capability_fit", "公司能力匹配", 15], ["local_position", "属地资源基础", 10], ["competition", "竞争态势", 10], ["risk_control", "风险可控性", 5]
];

export default async function OpportunityDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const item = await getOpportunity(id);
  if (!item) notFound();

  return (
    <>
      <header className="page-head">
        <div><div className="eyebrow">Opportunity Intelligence</div><h1>{item.title}</h1><div className="muted">{item.country} · {item.sector} · {item.stage}</div></div>
        <div><span className={`badge badge-${item.grade.toLowerCase()}`}>{item.grade} 级</span></div>
      </header>

      <section className="kpi-grid">
        <div className="card"><div className="kpi-label">机会评分</div><div className="kpi-value">{item.score}</div><div className="kpi-note">100 分规则引擎</div></div>
        <div className="card"><div className="kpi-label">研判置信度</div><div className="kpi-value">{item.confidence}%</div><div className="kpi-note">与机会分分离计算</div></div>
        <div className="card"><div className="kpi-label">决策建议</div><div className="kpi-value" style={{ fontSize: 22 }}>{item.decision}</div><div className="kpi-note">人工最终确认</div></div>
        <div className="card"><div className="kpi-label">估算规模</div><div className="kpi-value" style={{ fontSize: 22 }}>{item.estimated_value_usd_m ? `$${item.estimated_value_usd_m}M` : "待核实"}</div><div className="kpi-note">示范字段</div></div>
      </section>

      <div className="detail-grid">
        <div className="stack">
          <section className="section"><h2>经营判断</h2><p>{item.pursuit_thesis}</p><div className="eyebrow" style={{ marginTop: 18 }}>Next Actions</div><ol className="action-list">{item.next_actions.map((x) => <li key={x}>{x}</li>)}</ol></section>
          <section className="section"><h2>100 分评分拆解</h2><div className="score-list">{scoreMeta.map(([key, label, max]) => { const value = item.breakdown[key]; return <div className="score-row" key={key}><div><div>{label}<span className="muted"> / {max}</span></div><div className="bar"><span style={{ width: `${Math.min(100, value / max * 100)}%` }} /></div></div><strong>{value}</strong></div>; })}</div></section>
          <section className="section"><h2>证据链</h2>{item.evidence.length ? item.evidence.map((ev) => <div className="evidence" key={ev.id}><div><span className="source-rank">{ev.rank}级来源</span><strong>{ev.title}</strong></div><div className="muted" style={{ fontSize: 12, margin: "5px 0" }}>{ev.publisher} · {ev.published_at}</div><div>{ev.fact}</div></div>) : <div className="muted">暂无已绑定证据。</div>}</section>
        </div>
        <div className="stack">
          <section className="section"><h2>评分变化</h2><div className="timeline">{item.score_history.map((s) => <div key={s.date}><strong>{s.date} · {s.total} / {s.grade}</strong><div className="muted" style={{ marginTop: 5 }}>{s.note}</div></div>)}</div></section>
          <section className="section"><h2>项目画像</h2><table className="table"><tbody><tr><td className="muted">业主</td><td>{item.owner}</td></tr><tr><td className="muted">区域</td><td>{item.region}</td></tr><tr><td className="muted">阶段</td><td>{item.stage}</td></tr><tr><td className="muted">数据性质</td><td>{item.is_demo ? "脱敏示范数据" : "公开项目数据"}</td></tr></tbody></table></section>
        </div>
      </div>
    </>
  );
}

import Link from "next/link";

type Opportunity = { id:string; title:string; country:string; sector:string; stage:string; score:number; grade:string; confidence:number; pursuit_thesis:string; summary:string; next_actions:string[] };
const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function getOpportunities(): Promise<Opportunity[]> {
  try { const r = await fetch(`${API}/api/opportunities`, { cache:"no-store" }); if (r.ok) return r.json(); } catch {}
  return [];
}
async function getStrategy(id:string) {
  try { const r = await fetch(`${API}/api/opportunities/${id}/strategy`, { cache:"no-store" }); if (r.ok) return r.json(); } catch {}
  return null;
}

export default async function StrategyPage({ searchParams }:{ searchParams:Promise<{id?:string}> }) {
  const params = await searchParams;
  const opportunities = await getOpportunities();
  const selected = opportunities.find(x=>x.id===params.id) ?? opportunities[0];
  const workspace = selected ? await getStrategy(selected.id) : null;
  const strategy = workspace?.strategy;
  return <>
    <div className="page-head"><div><div className="eyebrow">HOW TO WIN · 怎么拿</div><h1>赢标经营策略</h1><p className="muted">把项目评分进一步转化为客户、竞争、差异化和经营动作。</p></div></div>
    <div className="strategy-tabs">{opportunities.slice(0,6).map(x=><Link key={x.id} className={selected?.id===x.id?"strategy-tab active":"strategy-tab"} href={`/strategy?id=${x.id}`}>{x.title}</Link>)}</div>
    {!selected ? <div className="section">暂无正式机会。</div> : <>
      <section className="section strategy-hero"><div><span className="eyebrow">{selected.country} · {selected.sector}</span><h2>{selected.title}</h2><p>{selected.stage}</p></div><div><span>机会评分</span><strong>{selected.score}/{selected.grade}</strong></div><div><span>策略成熟度</span><strong>{workspace?.readiness ?? 0}%</strong><small>{workspace?.readiness_label ?? "待建立"}</small></div></section>
      <div className="grid-2 strategy-grid">
        <div className="stack">
          <section className="section"><h2>赢标主张</h2><p className="strategy-statement">{strategy?.win_theme || selected.pursuit_thesis}</p><div className="policy-note">不是“我们能力很强”，而是明确回答：客户为什么应该选择我们。</div></section>
          <section className="section"><h2>客户核心诉求</h2><p>{strategy?.client_need || selected.summary}</p></section>
          <section className="section"><h2>差异化优势</h2>{strategy?.differentiation?.length ? <ul className="action-list">{strategy.differentiation.map((x:string)=><li key={x}>{x}</li>)}</ul> : <p className="muted">尚未形成证据化差异优势。需要结合类似业绩、融资协同、属地资源和交付能力补齐。</p>}</section>
          <section className="section"><h2>竞争格局</h2>{strategy?.competitors?.length ? strategy.competitors.map((x:any)=><div className="strategy-entity" key={x.name}><strong>{x.name}</strong><span>{x.position} · 置信度 {x.confidence}%</span><p>{x.evidence || "证据待补"}</p></div>) : <p className="muted">尚未建立竞争对手画像。不要在缺乏证据时推测对手报价或关系。</p>}</section>
        </div>
        <div className="stack">
          <section className="section"><h2>策略缺口</h2><ul className="action-list">{(strategy?.gaps?.length?strategy.gaps:workspace?.evidence_warnings ?? []).map((x:string)=><li key={x}>{x}</li>)}</ul></section>
          <section className="section"><h2>客户决策链</h2>{strategy?.stakeholders?.length ? strategy.stakeholders.map((x:any)=><div className="strategy-entity" key={`${x.organization}-${x.name}`}><strong>{x.name}</strong><span>{x.organization} · {x.role}</span><p>影响力 {x.influence} · 态度 {x.stance} · 置信度 {x.confidence}%</p></div>) : <p className="muted">暂无经证据核实的关键人。后续应区分决策者、影响者、技术评审和资金方。</p>}</section>
          <section className="section"><h2>下一轮经营战役</h2><ol className="action-list">{(strategy?.next_moves?.length?strategy.next_moves:selected.next_actions).map((x:string)=><li key={x}>{x}</li>)}</ol><div className="policy-note">策略保存后，新增战役动作会同步进入“重点跟踪”的经营行动清单。</div></section>
          <section className="section"><h2>证据纪律</h2><p className="muted">竞争关系、客户态度和关键人影响力属于高风险判断。智拓允许记录“未知”，但不允许把猜测包装成事实。所有关键判断应保留来源和置信度。</p></section>
        </div>
      </div>
    </>}
  </>;
}

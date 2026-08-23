import Link from "next/link";
import { getOpportunities } from "@/lib/api";

export default async function DashboardPage() {
  const opportunities = await getOpportunities();
  if (!opportunities.length) {
    return <div className="empty-state"><div className="eyebrow">ZHITUO</div><h1>海外市场经营总览</h1><p>当前暂无机会数据。可先初始化 Demo 数据，或从商机发现工作台导入公开项目线索。</p><div className="flow-links"><Link href="/discover">开始发现商机 →</Link></div></div>;
  }
  const aCount = opportunities.filter((item) => item.grade === "A").length;
  const avgScore = Math.round(opportunities.reduce((sum, item) => sum + item.score, 0) / opportunities.length);
  const hero = opportunities.find(x=>x.id==="west-africa-port-access-corridor") ?? opportunities[0];

  return <>
    <header className="page-head"><div><div className="eyebrow">STRATEGIC MARKET INTELLIGENCE</div><h1>中港智拓 · 海外市场经营智能体</h1><div className="muted">把“找信息、看机会、定策略”串成一条可追溯、可协同、可持续迭代的经营闭环。</div></div><Link className="primary-button demo-entry" href={`/strategy?id=${hero.id}`}>进入英雄 Demo</Link></header>

    <section className="three-questions">
      <Link href="/radar"><span>01</span><div><div className="eyebrow">WHERE TO PLAY</div><h2>去哪里</h2><p>从市场活跃度与经营吸引力识别值得投入资源的区域。</p></div></Link>
      <Link href="/tracking"><span>02</span><div><div className="eyebrow">WHAT TO PURSUE</div><h2>追什么</h2><p>用证据、评分、动态重评和行动责任筛选并持续经营重点机会。</p></div></Link>
      <Link href="/strategy"><span>03</span><div><div className="eyebrow">HOW TO WIN</div><h2>怎么拿</h2><p>形成赢标主张、红队挑战、策略缺口和下一轮经营战役。</p></div></Link>
    </section>

    <section className="kpi-grid">
      <div className="card"><div className="kpi-label">机会池</div><div className="kpi-value">{opportunities.length}</div><div className="kpi-note">正式经营机会</div></div>
      <div className="card"><div className="kpi-label">A 级机会</div><div className="kpi-value">{aCount}</div><div className="kpi-note">建议重点投入经营资源</div></div>
      <div className="card"><div className="kpi-label">平均机会分</div><div className="kpi-value">{avgScore}</div><div className="kpi-note">规则引擎，不等于中标概率</div></div>
      <div className="card"><div className="kpi-label">高置信研判</div><div className="kpi-value">{opportunities.filter((x) => x.confidence >= 80).length}</div><div className="kpi-note">置信度 ≥ 80%</div></div>
    </section>

    <div className="grid-2">
      <section className="section hero-opportunity"><div className="eyebrow">HERO OPPORTUNITY</div><h2>{hero.title}</h2><div className="muted">{hero.country} · {hero.sector} · {hero.stage}</div><div className="hero-score"><div className="score-big">{hero.score}</div><div><span className={`badge badge-${hero.grade.toLowerCase()}`}>{hero.grade} 级</span><div className="muted small" style={{marginTop:8}}>研判置信度 {hero.confidence}%</div></div></div><p>{hero.pursuit_thesis}</p><div className="hero-actions"><Link href={`/opportunities/${hero.id}`}>查看研判</Link><Link href={`/tracking`}>进入跟踪</Link><Link href={`/strategy?id=${hero.id}`}>制定策略</Link><Link href={`/battlecard?id=${hero.id}`}>查看作战卡</Link></div></section>
      <section className="section"><div className="section-head"><h2>产品闭环</h2><span className="muted small">AI + 规则 + 人工确认</span></div><div className="journey"><div><b>公开信息</b><span>URL / 公告 / 新闻 / 融资信息</span></div><i>→</i><div><b>商机与证据</b><span>Draft / Evidence / Score</span></div><i>→</i><div><b>经营策略</b><span>Tracking / Strategy / Red Team</span></div><i>→</i><div><b>行动与决策</b><span>Actions / Alerts / Battlecard</span></div></div><div className="policy-note">关键经营事实必须有来源；系统允许“未知”，不允许 AI 为完整性补造客户关系、竞争报价和领导态度。</div></section>
    </div>
  </>;
}

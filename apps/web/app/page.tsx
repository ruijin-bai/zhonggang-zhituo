import Link from "next/link";
import { getOpportunities } from "@/lib/api";

export default async function DashboardPage() {
  const opportunities = await getOpportunities();
  const aCount = opportunities.filter((item) => item.grade === "A").length;
  const avgScore = Math.round(opportunities.reduce((sum, item) => sum + item.score, 0) / opportunities.length);
  const hero = opportunities[0];

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Strategic Market Intelligence</div>
          <h1>海外市场经营总览</h1>
          <div className="muted">让 AI 帮助回答：去哪里、追什么、怎么拿。</div>
        </div>
        <div className="badge">工程化基线 v0.1</div>
      </header>

      <section className="kpi-grid">
        <div className="card"><div className="kpi-label">机会池</div><div className="kpi-value">{opportunities.length}</div><div className="kpi-note">当前工程样本</div></div>
        <div className="card"><div className="kpi-label">A 级机会</div><div className="kpi-value">{aCount}</div><div className="kpi-note">建议重点经营</div></div>
        <div className="card"><div className="kpi-label">平均机会分</div><div className="kpi-value">{avgScore}</div><div className="kpi-note">100 分规则引擎</div></div>
        <div className="card"><div className="kpi-label">高置信研判</div><div className="kpi-value">{opportunities.filter((x) => x.confidence >= 80).length}</div><div className="kpi-note">置信度 ≥ 80%</div></div>
      </section>

      <div className="grid-2">
        <section className="section hero-opportunity">
          <div className="eyebrow">Hero Opportunity</div>
          <h2 style={{ marginTop: 8 }}>{hero.title}</h2>
          <div className="muted">{hero.country} · {hero.sector} · {hero.stage}</div>
          <div className="hero-score">
            <div className="score-big">{hero.score}</div>
            <div><span className="badge badge-a">{hero.grade} 级</span><div className="delta" style={{ marginTop: 8 }}>72 → 81（+9）</div></div>
          </div>
          <p>{hero.pursuit_thesis}</p>
          <div className="flow"><strong>新证据</strong> → 融资确定 → 项目成熟 → 自动重评 → 策略更新</div>
          <div style={{ marginTop: 18 }}><Link href={`/opportunities/${hero.id}`}><strong>进入完整研判 →</strong></Link></div>
        </section>

        <section className="section">
          <div className="section-head"><h2>重点机会</h2><Link href="/opportunities">查看全部</Link></div>
          <table className="table"><tbody>
            {opportunities.map((item) => (
              <tr key={item.id}>
                <td><Link href={`/opportunities/${item.id}`}><strong>{item.title}</strong></Link><div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{item.country} · {item.sector}</div></td>
                <td className="score">{item.score}</td>
                <td><span className={`badge badge-${item.grade.toLowerCase()}`}>{item.grade}</span></td>
              </tr>
            ))}
          </tbody></table>
        </section>
      </div>
    </>
  );
}

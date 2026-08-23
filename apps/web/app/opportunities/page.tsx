import Link from "next/link";
import { getOpportunities } from "@/lib/api";

export default async function OpportunitiesPage() {
  const opportunities = await getOpportunities();
  return (
    <>
      <header className="page-head"><div><div className="eyebrow">Opportunity Pipeline</div><h1>海外工程机会池</h1><div className="muted">统一比较项目价值、证据充分度与经营优先级。</div></div></header>
      <section className="section">
        <table className="table">
          <thead><tr><th>项目机会</th><th>国别/区域</th><th>阶段</th><th>评分</th><th>置信度</th><th>建议</th></tr></thead>
          <tbody>{opportunities.map((item) => (
            <tr key={item.id}>
              <td><Link href={`/opportunities/${item.id}`}><strong>{item.title}</strong></Link><div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{item.sector}</div></td>
              <td>{item.country}<div className="muted" style={{ fontSize: 12 }}>{item.region}</div></td>
              <td>{item.stage}</td><td><span className="score">{item.score}</span> <span className={`badge badge-${item.grade.toLowerCase()}`}>{item.grade}</span></td>
              <td>{item.confidence}%</td><td><strong>{item.decision}</strong></td>
            </tr>
          ))}</tbody>
        </table>
      </section>
    </>
  );
}

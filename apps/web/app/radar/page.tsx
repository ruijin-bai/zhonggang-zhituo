import Link from "next/link";

import { getRadar } from "../../lib/api";

function valueText(value: number | null) {
  if (value === null) return "待核实";
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}bn`;
  return `$${value.toFixed(0)}m`;
}

export default async function RadarPage() {
  const radar = await getRadar();
  const leader = radar.countries[0];

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Market Radar · Where to Play</div>
          <h1>市场雷达</h1>
          <div className="muted">把分散商机转成国别与专业维度的经营资源配置判断。</div>
        </div>
        <Link className="primary-button" href="/discover">扫描新来源</Link>
      </header>

      <div className="kpi-grid">
        <div className="card"><div className="kpi-label">覆盖国别</div><div className="kpi-value">{radar.country_count}</div><div className="kpi-note">已有正式机会或待确认草稿</div></div>
        <div className="card"><div className="kpi-label">正式机会</div><div className="kpi-value">{radar.opportunity_count}</div><div className="kpi-note">进入持续经营研判的项目</div></div>
        <div className="card"><div className="kpi-label">待确认发现</div><div className="kpi-value">{radar.pending_draft_count}</div><div className="kpi-note">尚未污染正式机会池</div></div>
        <div className="card"><div className="kpi-label">证据沉淀</div><div className="kpi-value">{radar.evidence_count}</div><div className="kpi-note">已绑定项目的结构化 Evidence</div></div>
      </div>

      {leader ? (
        <section className="section radar-lead">
          <div className="eyebrow">当前优先观察</div>
          <div className="radar-lead-grid">
            <div><h2>{leader.country} · {leader.region}</h2><p className="muted">{leader.top_sectors.join(" / ") || "专业待进一步识别"}</p></div>
            <div><span>经营吸引力</span><strong>{leader.attractiveness_index ?? "待证据"}</strong></div>
            <div><span>市场活跃度</span><strong>{leader.activity_index}</strong></div>
            <div><span>机会规模</span><strong>{valueText(leader.total_value_usd_m)}</strong></div>
          </div>
        </section>
      ) : null}

      <div className="grid-2 radar-grid">
        <section className="section">
          <div className="section-head"><h2>国别经营雷达</h2><span className="muted">吸引力 ≠ 活跃度</span></div>
          <div className="radar-country-list">
            {radar.countries.map((item, index) => (
              <div className="radar-country" key={item.country}>
                <div className="radar-rank">{String(index + 1).padStart(2, "0")}</div>
                <div className="radar-country-main">
                  <div className="radar-country-title"><strong>{item.country}</strong><span>{item.region}</span></div>
                  <div className="radar-bars">
                    <div><span>经营吸引力</span><div className="bar"><i style={{ width: `${item.attractiveness_index ?? 0}%` }} /></div><b>{item.attractiveness_index ?? "—"}</b></div>
                    <div><span>市场活跃度</span><div className="bar"><i style={{ width: `${item.activity_index}%` }} /></div><b>{item.activity_index}</b></div>
                  </div>
                  <div className="radar-meta">{item.opportunity_count} 个正式机会 · {item.pending_draft_count} 个草稿 · {item.high_grade_count} 个 A 级 · {item.top_sectors.join(" / ") || "专业待识别"}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="stack">
          <section className="section">
            <h2>专业机会结构</h2>
            {radar.sectors.length ? (
              <table className="table">
                <thead><tr><th>专业</th><th>机会</th><th>A级</th><th>均分</th></tr></thead>
                <tbody>{radar.sectors.slice(0, 6).map((item) => <tr key={item.sector}><td>{item.sector}</td><td>{item.opportunity_count}</td><td>{item.high_grade_count}</td><td>{item.average_score ?? "—"}</td></tr>)}</tbody>
              </table>
            ) : <div className="muted">启动数据库后自动形成专业聚合。</div>}
          </section>
          <section className="section">
            <h2>雷达口径</h2>
            <p className="muted">{radar.note}</p>
            <div className="policy-note">经营吸引力只使用置信度达到判断阈值的正式机会；证据不足项目只贡献市场活跃度，不会因为未知字段为 0 而拉低一个国家。</div>
          </section>
        </div>
      </div>
    </>
  );
}

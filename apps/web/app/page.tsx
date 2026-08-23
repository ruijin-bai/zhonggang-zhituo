import Link from "next/link";
import { getOpportunities, getRadar } from "@/lib/api";

export default async function DashboardPage() {
  const [opportunities, radar] = await Promise.all([getOpportunities(), getRadar()]);

  if (!opportunities.length) {
    return (
      <div className="empty-state">
        <div className="eyebrow">ZHITUO</div>
        <h1>海外市场经营总览</h1>
        <p>当前暂无正式机会数据。可以先从公开来源发现商机，再人工确认进入机会池。</p>
        <div className="flow-links">
          <Link href="/discover">开始发现商机 →</Link>
          <Link href="/radar">查看市场雷达 →</Link>
        </div>
      </div>
    );
  }

  const aCount = opportunities.filter((item) => item.grade === "A").length;
  const rated = opportunities.filter((item) => item.confidence >= 45);
  const avgScore = rated.length
    ? Math.round(rated.reduce((sum, item) => sum + item.score, 0) / rated.length)
    : 0;
  const hero = opportunities.find((item) => item.id === "west-africa-port-access-corridor") ?? opportunities[0];
  const marketLeader = radar.countries[0];
  const highConfidence = opportunities.filter((item) => item.confidence >= 80).length;

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">STRATEGIC MARKET INTELLIGENCE</div>
          <h1>中港智拓 · 海外市场经营驾驶舱</h1>
          <div className="muted">从市场扫描到重点跟踪，再到赢标策略与行动闭环，把海外经营关键判断统一到同一套证据和数据底座上。</div>
        </div>
        <Link className="primary-button demo-entry" href={`/strategy?id=${hero.id}`}>进入英雄 Demo</Link>
      </header>

      <section className="three-questions">
        <Link href="/radar">
          <span>01</span>
          <div>
            <div className="eyebrow">WHERE TO PLAY</div>
            <h2>去哪里</h2>
            <p>{marketLeader ? `当前优先观察：${marketLeader.country}，经营吸引力 ${marketLeader.attractiveness_index ?? "待证据"}。` : "从市场活跃度与经营吸引力识别值得投入资源的区域。"}</p>
          </div>
        </Link>
        <Link href="/tracking">
          <span>02</span>
          <div>
            <div className="eyebrow">WHAT TO PURSUE</div>
            <h2>追什么</h2>
            <p>{aCount ? `当前 ${aCount} 个 A 级机会，应优先配置经营资源并持续补齐证据。` : "用证据、评分、动态重评和行动责任筛选并持续经营重点机会。"}</p>
          </div>
        </Link>
        <Link href={`/strategy?id=${hero.id}`}>
          <span>03</span>
          <div>
            <div className="eyebrow">HOW TO WIN</div>
            <h2>怎么拿</h2>
            <p>针对重点机会形成赢标主张、红队挑战、策略缺口与下一轮经营行动。</p>
          </div>
        </Link>
      </section>

      <section className="cockpit-strip">
        <Link href="/radar"><span>市场覆盖</span><strong>{radar.country_count}</strong><small>个国别/区域进入雷达</small></Link>
        <Link href="/discover"><span>待确认发现</span><strong>{radar.pending_draft_count}</strong><small>条草稿等待人工确认</small></Link>
        <Link href="/opportunities"><span>正式机会</span><strong>{opportunities.length}</strong><small>其中 A 级 {aCount} 个</small></Link>
        <Link href="/intelligence"><span>证据沉淀</span><strong>{radar.evidence_count}</strong><small>结构化 Evidence</small></Link>
        <Link href="/tracking"><span>高置信研判</span><strong>{highConfidence}</strong><small>置信度 ≥ 80%</small></Link>
      </section>

      <div className="grid-2 cockpit-main">
        <section className="section hero-opportunity">
          <div className="eyebrow">HERO OPPORTUNITY · WHAT TO PURSUE</div>
          <h2>{hero.title}</h2>
          <div className="muted">{hero.country} · {hero.sector} · {hero.stage}</div>
          <div className="hero-score">
            <div className="score-big">{hero.score}</div>
            <div>
              <span className={`badge badge-${hero.grade.toLowerCase()}`}>{hero.grade} 级</span>
              <div className="muted small" style={{ marginTop: 8 }}>研判置信度 {hero.confidence}% · {hero.decision}</div>
            </div>
          </div>
          <p>{hero.pursuit_thesis}</p>
          <div className="hero-actions">
            <Link href={`/opportunities/${hero.id}`}>查看研判</Link>
            <Link href="/tracking">进入跟踪</Link>
            <Link href={`/strategy?id=${hero.id}`}>制定策略</Link>
            <Link href={`/battlecard?id=${hero.id}`}>查看作战卡</Link>
          </div>
        </section>

        <section className="section market-signal-card">
          <div className="section-head"><h2>市场信号 · WHERE TO PLAY</h2><Link href="/radar">进入雷达 →</Link></div>
          {marketLeader ? (
            <>
              <div className="market-leader">
                <div><span>优先观察国别</span><strong>{marketLeader.country}</strong><small>{marketLeader.region}</small></div>
                <div><span>经营吸引力</span><strong>{marketLeader.attractiveness_index ?? "—"}</strong><small>基于高置信正式机会</small></div>
                <div><span>市场活跃度</span><strong>{marketLeader.activity_index}</strong><small>机会、草稿、来源与证据</small></div>
              </div>
              <div className="policy-note">重点专业：{marketLeader.top_sectors.join(" / ") || "待进一步识别"}。吸引力用于横向聚焦，不替代正式国别战略决策。</div>
            </>
          ) : <div className="muted">暂无足够国别数据。</div>}
        </section>
      </div>

      <section className="section cockpit-journey">
        <div className="section-head"><h2>经营闭环</h2><span className="muted small">AI + 规则 + 人工确认</span></div>
        <div className="journey">
          <Link href="/discover"><b>1. 发现</b><span>URL / 公告 / 新闻 → Opportunity Draft</span></Link><i>→</i>
          <Link href="/intelligence"><b>2. 研判</b><span>Source / Evidence → Score / Re-score</span></Link><i>→</i>
          <Link href="/tracking"><b>3. 跟踪</b><span>Watch / Alerts / Actions → 持续经营</span></Link><i>→</i>
          <Link href={`/strategy?id=${hero.id}`}><b>4. 策略</b><span>Strategy / Red Team → How to Win</span></Link><i>→</i>
          <Link href={`/battlecard?id=${hero.id}`}><b>5. 决策</b><span>Battlecard → 经营会议与行动</span></Link>
        </div>
        <div className="policy-note">当前正式机会平均分 {avgScore}。系统允许“未知”和“证据不足”，不允许 AI 为完整性补造客户关系、竞争报价、领导态度或中标概率。</div>
      </section>
    </>
  );
}

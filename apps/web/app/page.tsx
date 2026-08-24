import Link from "next/link";

import { getOpportunities, getRadar } from "@/lib/api";
import { getDailyBrief, type DailyBrief } from "@/lib/operating";

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function attentionHref(item: DailyBrief["attention"][number]): string {
  if (item.kind === "candidate_review") return `/knowledge/candidates/${encodeURIComponent(item.resource_id)}`;
  if (item.opportunity_id) return `/knowledge/opportunities/${encodeURIComponent(item.opportunity_id)}`;
  return "/tracking";
}

function attentionLabel(kind: DailyBrief["attention"][number]["kind"]): string {
  return {
    overdue_action: "逾期行动",
    open_alert: "经营预警",
    review_due: "到期复盘",
    candidate_review: "待审商机",
  }[kind];
}

export default async function DashboardPage() {
  const briefPromise = getDailyBrief(24, 8).catch(() => null);
  const [opportunities, radar, brief] = await Promise.all([getOpportunities(), getRadar(), briefPromise]);

  const aCount = opportunities.filter((item) => item.grade === "A").length;
  const rated = opportunities.filter((item) => item.confidence >= 45);
  const avgScore = rated.length
    ? Math.round(rated.reduce((sum, item) => sum + item.score, 0) / rated.length)
    : 0;
  const focus = [...opportunities].sort((a, b) => b.score - a.score || b.confidence - a.confidence)[0] ?? null;
  const marketLeader = radar.countries[0];
  const highConfidence = opportunities.filter((item) => item.confidence >= 80).length;

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">SYSTEM OF INTELLIGENCE · OVERSEAS ENGINEERING</div>
          <h1>中港智拓 · 海外工程经营智能中枢</h1>
          <div className="muted">持续感知市场、识别机会、汇聚证据、辅助判断并推动经营行动，把分散信息转化为组织可复用的经营能力。</div>
        </div>
        <Link className="primary-button" href="/knowledge">进入经营情报</Link>
      </header>

      <section className="section" style={{ marginBottom: 18 }}>
        <div className="section-head">
          <div>
            <div className="eyebrow">DAILY OPERATING BRIEF</div>
            <h2 style={{ marginBottom: 4 }}>今天发生什么 · 我需要处理什么</h2>
            <div className="muted small">过去 {brief?.window_hours ?? 24} 小时的经营变化与当前待处理事项</div>
          </div>
          {brief ? <span className="muted small">生成于 {formatDate(brief.generated_at)}</span> : null}
        </div>

        {brief ? (
          <>
            <div className="cockpit-strip" style={{ marginTop: 14 }}>
              <Link href="/knowledge"><span>新增候选</span><strong>{brief.summary.new_candidates}</strong><small>待审共 {brief.summary.pending_candidates}</small></Link>
              <Link href="/tracking"><span>逾期行动</span><strong>{brief.summary.overdue_actions}</strong><small>7 日内到期 {brief.summary.due_soon_actions}</small></Link>
              <Link href="/tracking"><span>未关闭预警</span><strong>{brief.summary.open_alerts}</strong><small>需要经营处置</small></Link>
              <Link href="/tracking"><span>到期复盘</span><strong>{brief.summary.review_due}</strong><small>重点机会 Review</small></Link>
              <Link href="/knowledge"><span>最近变化</span><strong>{brief.summary.recent_events}</strong><small>过去 {brief.window_hours} 小时 Event</small></Link>
            </div>

            <div className="grid-2" style={{ marginTop: 16 }}>
              <div>
                <div className="section-head"><h2>优先处理</h2><span className="muted small">按风险与时效排序</span></div>
                {brief.attention.length ? (
                  <div className="stack">
                    {brief.attention.slice(0, 8).map((item) => (
                      <Link className="evidence" href={attentionHref(item)} key={`${item.kind}-${item.resource_id}`} style={{ textDecoration: "none", color: "inherit" }}>
                        <div>
                          <span className="source-rank">{attentionLabel(item.kind)}</span>
                          <strong>{item.title}</strong>
                        </div>
                        <div className="muted small" style={{ marginTop: 6 }}>{item.subtitle}</div>
                        {item.due_at ? <div className="muted small" style={{ marginTop: 4 }}>时间：{formatDate(item.due_at)}</div> : null}
                        {item.message ? <div style={{ marginTop: 5 }}>{item.message}</div> : null}
                      </Link>
                    ))}
                  </div>
                ) : <div className="muted">当前没有需要优先处理的 Candidate、逾期行动、预警或到期复盘。</div>}
              </div>

              <div>
                <div className="section-head"><h2>最近经营变化</h2><Link href="/knowledge">检索全部情报 →</Link></div>
                {brief.recent_events.length ? (
                  <div className="timeline">
                    {brief.recent_events.map((event, index) => (
                      <div key={`${event.opportunity_id}-${event.occurred_at}-${index}`}>
                        <Link href={`/knowledge/opportunities/${encodeURIComponent(event.opportunity_id)}`}><strong>{event.title}</strong></Link>
                        <div className="muted small" style={{ marginTop: 4 }}>{event.event_type} · {formatDate(event.occurred_at)}</div>
                      </div>
                    ))}
                  </div>
                ) : <div className="muted">过去 {brief.window_hours} 小时暂无新的 Opportunity Event。</div>}
              </div>
            </div>
            <div className="policy-note" style={{ marginTop: 14 }}>{brief.note}</div>
          </>
        ) : (
          <div className="error-box" style={{ marginTop: 14 }}>实时经营晨报暂不可用。生产模式不会用 Demo 数据伪装实时待办，请检查认证、API 和数据库状态。</div>
        )}
      </section>

      <section className="three-questions">
        <Link href="/radar">
          <span>01</span>
          <div>
            <div className="eyebrow">WHERE TO PLAY</div>
            <h2>去哪里</h2>
            <p>{marketLeader ? `当前优先观察：${marketLeader.country}，经营吸引力 ${marketLeader.attractiveness_index ?? "待证据"}。` : "从市场活跃度、经营吸引力与证据质量识别值得投入资源的区域。"}</p>
          </div>
        </Link>
        <Link href="/opportunities">
          <span>02</span>
          <div>
            <div className="eyebrow">WHAT TO PURSUE</div>
            <h2>追什么</h2>
            <p>{aCount ? `当前 ${aCount} 个 A 级机会，应优先配置经营资源并持续补齐证据。` : "用证据、评分、动态重评和人工审核筛选重点机会。"}</p>
          </div>
        </Link>
        <Link href={focus ? `/strategy?id=${encodeURIComponent(focus.id)}` : "/opportunities"}>
          <span>03</span>
          <div>
            <div className="eyebrow">HOW TO WIN</div>
            <h2>怎么拿</h2>
            <p>针对重点机会形成赢标主张、红队挑战、资源缺口和下一轮可执行经营行动。</p>
          </div>
        </Link>
      </section>

      <section className="cockpit-strip">
        <Link href="/radar"><span>市场覆盖</span><strong>{radar.country_count}</strong><small>个国别/区域进入雷达</small></Link>
        <Link href="/knowledge"><span>待审 Candidate</span><strong>{brief?.summary.pending_candidates ?? radar.pending_draft_count}</strong><small>人工确认后才进入正式机会</small></Link>
        <Link href="/opportunities"><span>正式机会</span><strong>{opportunities.length}</strong><small>其中 A 级 {aCount} 个</small></Link>
        <Link href="/knowledge"><span>证据沉淀</span><strong>{radar.evidence_count}</strong><small>结构化 Evidence</small></Link>
        <Link href="/tracking"><span>高置信研判</span><strong>{highConfidence}</strong><small>置信度 ≥ 80%</small></Link>
      </section>

      <div className="grid-2 cockpit-main">
        <section className="section hero-opportunity">
          <div className="eyebrow">PRIORITY OPPORTUNITY · WHAT TO PURSUE</div>
          {focus ? (
            <>
              <h2>{focus.title}</h2>
              <div className="muted">{focus.country} · {focus.sector} · {focus.stage}</div>
              <div className="hero-score">
                <div className="score-big">{focus.score}</div>
                <div>
                  <span className={`badge badge-${focus.grade.toLowerCase()}`}>{focus.grade} 级</span>
                  <div className="muted small" style={{ marginTop: 8 }}>研判置信度 {focus.confidence}% · {focus.decision}</div>
                </div>
              </div>
              <p>{focus.pursuit_thesis}</p>
              <div className="hero-actions">
                <Link href={`/knowledge/opportunities/${encodeURIComponent(focus.id)}`}>360°知识视图</Link>
                <Link href={`/opportunities/${encodeURIComponent(focus.id)}`}>查看研判</Link>
                <Link href="/tracking">进入跟踪</Link>
                <Link href={`/strategy?id=${encodeURIComponent(focus.id)}`}>经营策略</Link>
              </div>
            </>
          ) : (
            <div className="empty-state" style={{ minHeight: 220 }}>
              <h2>当前暂无正式 Opportunity</h2>
              <p>先处理待审 Candidate；系统不会在未经人工确认和证据校验的情况下自动生成正式经营机会。</p>
              <div className="flow-links"><Link href="/knowledge">进入 Candidate Inbox →</Link></div>
            </div>
          )}
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
        <div className="section-head"><h2>智能中枢闭环</h2><span className="muted small">感知 · 判断 · 协同 · 记忆 · 学习</span></div>
        <div className="journey">
          <Link href="/knowledge"><b>1. 感知</b><span>Source → Candidate → Entity / Evidence</span></Link><i>→</i>
          <Link href="/opportunities"><b>2. 判断</b><span>Opportunity → Score / Confidence / Re-score</span></Link><i>→</i>
          <Link href="/tracking"><b>3. 协同</b><span>Watch / Alert / Action → 责任与执行</span></Link><i>→</i>
          <Link href="/knowledge/entities"><b>4. 记忆</b><span>Entity / Knowledge → 企业经营资产</span></Link><i>→</i>
          <div><b>5. 学习</b><span>Outcome / Win-Loss → 后续阶段校准</span></div>
        </div>
        <div className="policy-note">当前正式机会平均分 {avgScore}。系统允许“未知”和“证据不足”，不允许 AI 为完整性补造客户关系、竞争报价、领导态度或中标概率。</div>
      </section>
    </>
  );
}

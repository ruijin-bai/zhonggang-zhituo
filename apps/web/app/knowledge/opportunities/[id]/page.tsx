import Link from "next/link";
import { notFound } from "next/navigation";

import { getOpportunityKnowledge } from "@/lib/knowledge";
import styles from "../../knowledge.module.css";

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function payloadSummary(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload).slice(0, 4);
  if (!entries.length) return "无附加字段";
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(" · ");
}

export default async function OpportunityKnowledgePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let view;
  try {
    view = await getOpportunityKnowledge(id);
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("404")) notFound();
    throw error;
  }

  const { opportunity } = view;

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Opportunity 360° Knowledge View</div>
          <h1>{opportunity.title}</h1>
          <div className="muted">
            {opportunity.country} · {opportunity.region} · {opportunity.sector} · {opportunity.stage}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span className={`badge badge-${opportunity.grade.toLowerCase()}`}>{opportunity.grade} 级</span>
          <Link className="primary-button" href={`/opportunities/${encodeURIComponent(opportunity.id)}`}>
            返回机会研判
          </Link>
        </div>
      </header>

      <section className={styles.heroMetrics}>
        <div className={styles.heroMetric}><span>机会评分</span><strong>{opportunity.score}</strong></div>
        <div className={styles.heroMetric}><span>研判置信度</span><strong>{opportunity.confidence}%</strong></div>
        <div className={styles.heroMetric}><span>正式来源</span><strong>{view.provenance.formal_source_count}</strong></div>
        <div className={styles.heroMetric}><span>不可变原件</span><strong>{view.provenance.immutable_source_document_count}</strong></div>
      </section>

      <div className={styles.knowledgeGrid}>
        <section className={styles.knowledgeSection}>
          <div className={styles.sectionTitle}><h2>经营判断</h2><span className={styles.typeBadge}>{opportunity.decision}</span></div>
          <p>{opportunity.pursuit_thesis || opportunity.summary}</p>
          {opportunity.next_actions.length ? (
            <>
              <div className="eyebrow" style={{ marginTop: 18 }}>Next Actions</div>
              <ol className="action-list">
                {opportunity.next_actions.map((action) => <li key={action}>{action}</li>)}
              </ol>
            </>
          ) : <div className={styles.empty}>暂无下一步行动建议。</div>}
        </section>

        <section className={styles.knowledgeSection}>
          <div className={styles.sectionTitle}><h2>项目画像</h2><span className={styles.meta}>{opportunity.id}</span></div>
          <table className="table">
            <tbody>
              <tr><td className="muted">业主</td><td>{opportunity.owner || "待核实"}</td></tr>
              <tr><td className="muted">国家 / 区域</td><td>{opportunity.country} / {opportunity.region}</td></tr>
              <tr><td className="muted">专业</td><td>{opportunity.sector}</td></tr>
              <tr><td className="muted">阶段</td><td>{opportunity.stage}</td></tr>
              <tr><td className="muted">估算规模</td><td>{opportunity.estimated_value_usd_m === null ? "待核实" : `$${opportunity.estimated_value_usd_m}M`}</td></tr>
            </tbody>
          </table>
          <p className={styles.snippet}>{opportunity.summary}</p>
        </section>

        <section className={styles.knowledgeSection}>
          <div className={styles.sectionTitle}><h2>关键经营主体</h2><span className={styles.meta}>{view.entities.length} 个</span></div>
          {view.entities.length ? (
            <div className={styles.entityList}>
              {view.entities.map((entity) => (
                <article className={styles.entityCard} key={`${entity.entity_id}-${entity.role}`}>
                  <div className={styles.entityHeader}>
                    <strong>{entity.name}</strong>
                    <span className={styles.roleBadge}>{entity.role}</span>
                    <span className={styles.fieldBadge}>{Math.round(entity.confidence * 100)}% 置信</span>
                  </div>
                  <div className={styles.meta} style={{ marginTop: 6 }}>
                    {entity.country || "国别待核实"} · 支持来源 {entity.source_count}
                  </div>
                  {entity.aliases.length ? <div className={styles.snippet}>别名：{entity.aliases.join("、")}</div> : null}
                </article>
              ))}
            </div>
          ) : <div className={styles.empty}>暂无已解析经营主体。</div>}
        </section>

        <section className={styles.knowledgeSection}>
          <div className={styles.sectionTitle}><h2>相关机会</h2><span className={styles.meta}>按共享实体关联</span></div>
          {view.related_opportunities.length ? (
            <div className={styles.relatedList}>
              {view.related_opportunities.map((related) => (
                <article className={styles.relatedCard} key={related.opportunity_id}>
                  <Link className={styles.resultTitle} href={`/knowledge/opportunities/${encodeURIComponent(related.opportunity_id)}`}>
                    {related.title}
                  </Link>
                  <div className={styles.meta}>{related.country} · {related.sector} · {related.stage}</div>
                  <div className={styles.matched}>
                    {related.shared_entities.map((entity) => (
                      <span className={styles.fieldBadge} key={`${related.opportunity_id}-${entity.entity_id}-${entity.role_in_related}`}>
                        共享主体 · {entity.name} · {entity.role_in_related}
                      </span>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          ) : <div className={styles.empty}>当前没有通过已解析实体发现的相关正式机会。</div>}
        </section>

        <section className={`${styles.knowledgeSection} ${styles.fullWidth}`}>
          <div className={styles.sectionTitle}>
            <h2>证据事实</h2>
            <span className={styles.meta}>{view.evidence.length} 条 · Evidence-first</span>
          </div>
          {view.evidence.length ? (
            <div className={styles.evidenceList}>
              {view.evidence.map((evidence) => (
                <article className={styles.evidenceCard} key={evidence.evidence_id}>
                  <div className={styles.cardTop}>
                    <div className={styles.entityHeader}>
                      <span className={styles.rankBadge}>{evidence.rank} 级来源</span>
                      {evidence.field_name ? <span className={styles.fieldBadge}>{evidence.field_name}</span> : null}
                    </div>
                    <span className={styles.meta}>{Math.round(evidence.confidence * 100)}% 置信</span>
                  </div>
                  <div className={styles.evidenceQuote}>{evidence.fact}</div>
                  <div className={styles.meta} style={{ marginTop: 7 }}>{evidence.publisher}</div>
                  {evidence.source_url ? (
                    <a className={`${styles.resultTitle} ${styles.sourceUrl}`} href={evidence.source_url} target="_blank" rel="noreferrer">
                      打开公开来源
                    </a>
                  ) : null}
                </article>
              ))}
            </div>
          ) : <div className={styles.empty}>暂无正式 Evidence。</div>}
        </section>

        <section className={styles.knowledgeSection}>
          <div className={styles.sectionTitle}><h2>正式来源与原件 Provenance</h2><span className={styles.meta}>{view.sources.length} 条</span></div>
          {view.sources.length ? (
            <div className={styles.sourceList}>
              {view.sources.map((source) => (
                <article className={styles.sourceCard} key={source.source_id}>
                  <div className={styles.entityHeader}>
                    <span className={styles.rankBadge}>{source.source_rank} 级</span>
                    <strong>{source.title}</strong>
                  </div>
                  <div className={styles.meta}>{source.publisher} · {source.published_at}</div>
                  <div className={styles.snippet}>
                    {source.source_document_id ? `SourceDocument: ${source.source_document_id}` : "历史来源：未绑定不可变 SourceDocument"}
                  </div>
                  {source.url ? (
                    <a className={`${styles.resultTitle} ${styles.sourceUrl}`} href={source.url} target="_blank" rel="noreferrer">打开公开来源</a>
                  ) : null}
                </article>
              ))}
            </div>
          ) : <div className={styles.empty}>暂无正式来源。</div>}
        </section>

        <section className={styles.knowledgeSection}>
          <div className={styles.sectionTitle}><h2>经营事件</h2><span className={styles.meta}>最近 {view.events.length} 条</span></div>
          {view.events.length ? (
            <div className={styles.relatedList}>
              {view.events.map((event, index) => (
                <article className={styles.relatedCard} key={`${event.occurred_at}-${event.event_type}-${index}`}>
                  <strong>{event.event_type}</strong>
                  <div className={styles.meta}>{formatDate(event.occurred_at)}</div>
                  <div className={styles.snippet}>{payloadSummary(event.payload)}</div>
                </article>
              ))}
            </div>
          ) : <div className={styles.empty}>暂无经营事件。</div>}
        </section>
      </div>
    </>
  );
}

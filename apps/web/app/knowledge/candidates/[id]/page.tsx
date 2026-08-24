import Link from "next/link";
import { notFound } from "next/navigation";

import { getCandidate } from "@/lib/knowledge";
import { canReviewCandidates, getSessionMeta } from "@/lib/session";
import CandidateReview from "./candidate-review";
import styles from "../../knowledge.module.css";

export default async function CandidateReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let candidate;
  try {
    candidate = await getCandidate(id);
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("404")) notFound();
    throw error;
  }

  const meta = await getSessionMeta();
  const canReview = canReviewCandidates(meta.role);

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Candidate Opportunity Review</div>
          <h1>{candidate.discovery.title}</h1>
          <div className="muted">
            {candidate.discovery.country} · {candidate.discovery.sector} · {candidate.discovery.stage} · {candidate.status}
          </div>
        </div>
        <Link className="primary-button" href="/knowledge">返回经营情报</Link>
      </header>

      <section className={styles.heroMetrics}>
        <div className={styles.heroMetric}><span>识别置信度</span><strong>{Math.round(candidate.discovery.confidence * 100)}%</strong></div>
        <div className={styles.heroMetric}><span>支持来源</span><strong>{candidate.source_count}</strong></div>
        <div className={styles.heroMetric}><span>主体角色关系</span><strong>{candidate.entities.length}</strong></div>
        <div className={styles.heroMetric}><span>疑似正式机会</span><strong>{candidate.duplicate_matches.length}</strong></div>
      </section>

      <div className={styles.knowledgeGrid}>
        <div style={{ display: "grid", gap: 20 }}>
          <section className={styles.knowledgeSection}>
            <div className={styles.sectionTitle}><h2>机器识别项目画像</h2><span className={styles.typeBadge}>待人工确认</span></div>
            <table className="table">
              <tbody>
                <tr><td className="muted">业主</td><td>{candidate.discovery.owner}</td></tr>
                <tr><td className="muted">国家 / 区域</td><td>{candidate.discovery.country} / {candidate.discovery.region}</td></tr>
                <tr><td className="muted">专业</td><td>{candidate.discovery.sector}</td></tr>
                <tr><td className="muted">阶段</td><td>{candidate.discovery.stage}</td></tr>
                <tr><td className="muted">估算规模</td><td>{candidate.discovery.estimated_value_usd_m === null ? "待核实" : `$${candidate.discovery.estimated_value_usd_m}M`}</td></tr>
              </tbody>
            </table>
            <p className={styles.snippet}>{candidate.discovery.summary}</p>
          </section>

          <section className={styles.knowledgeSection}>
            <div className={styles.sectionTitle}><h2>支持来源</h2><span className={styles.meta}>{candidate.source_count} 份</span></div>
            <div className={styles.sourceList}>
              <article className={styles.sourceCard}>
                <div className={styles.entityHeader}>
                  <span className={styles.rankBadge}>{candidate.source_rank} 级</span>
                  <strong>{candidate.source_title}</strong>
                </div>
                <div className={styles.meta}>{candidate.publisher} · {candidate.published_at}</div>
                {candidate.source_url ? <a className={styles.resultTitle} href={candidate.source_url} target="_blank" rel="noreferrer">打开公开来源</a> : null}
              </article>
            </div>
            {candidate.source_document_ids.length ? (
              <div className={styles.snippet} style={{ marginTop: 10 }}>
                不可变 SourceDocument：{candidate.source_document_ids.join("、")}
              </div>
            ) : null}
          </section>

          <section className={styles.knowledgeSection}>
            <div className={styles.sectionTitle}><h2>识别事实</h2><span className={styles.meta}>{candidate.discovery.facts.length} 条</span></div>
            {candidate.discovery.facts.length ? (
              <div className={styles.evidenceList}>
                {candidate.discovery.facts.map((fact, index) => (
                  <article className={styles.evidenceCard} key={`${fact.field_name}-${index}`}>
                    <div className={styles.cardTop}>
                      <div className={styles.entityHeader}>
                        <span className={styles.fieldBadge}>{fact.field_name}</span>
                        <strong>{fact.value}</strong>
                      </div>
                      <span className={styles.meta}>{Math.round(fact.confidence * 100)}%</span>
                    </div>
                    <div className={styles.evidenceQuote}>{fact.evidence_quote}</div>
                  </article>
                ))}
              </div>
            ) : <div className={styles.empty}>当前来源未抽取到可用于评分的结构化事实。</div>}
          </section>

          <section className={styles.knowledgeSection}>
            <div className={styles.sectionTitle}><h2>经营主体</h2><span className={styles.meta}>{candidate.entities.length} 个角色关系</span></div>
            {candidate.entities.length ? (
              <div className={styles.entityList}>
                {candidate.entities.map((entity) => (
                  <article className={styles.entityCard} key={`${entity.id}-${entity.role}`}>
                    <Link className={styles.resultTitle} href={`/knowledge/entities/${encodeURIComponent(entity.id)}`}>{entity.name}</Link>
                    <div className={styles.meta}>{entity.country || "国别待核实"} · 来源 {entity.source_count}</div>
                    <div className={styles.matched}><span className={styles.roleBadge}>{entity.role}</span></div>
                  </article>
                ))}
              </div>
            ) : <div className={styles.empty}>当前尚未解析出经营主体。</div>}
          </section>
        </div>

        <div style={{ display: "grid", gap: 20, alignContent: "start" }}>
          <section className={styles.knowledgeSection}>
            <div className={styles.sectionTitle}><h2>审核上下文</h2><span className={styles.typeBadge}>{meta.role}</span></div>
            <div className={styles.snippet}>组织：{meta.organization}</div>
            <div className={styles.snippet}>审核动作由后端 RBAC、业务幂等和 Audit Log 共同保护；正式入池前会重新读取并校验 DocumentStore 原文。</div>
          </section>
          <CandidateReview candidate={candidate} canReview={canReview} />
        </div>
      </div>
    </>
  );
}

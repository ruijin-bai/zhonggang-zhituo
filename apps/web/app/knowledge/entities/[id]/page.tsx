import Link from "next/link";
import { notFound } from "next/navigation";

import { getEntity } from "@/lib/operating";
import styles from "../../knowledge.module.css";

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

export default async function EntityDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let entity;
  try {
    entity = await getEntity(id);
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("404")) notFound();
    throw error;
  }

  const roles = [...new Set(entity.opportunities.map((item) => item.role))];
  const sourceCount = entity.opportunities.reduce((sum, item) => sum + item.source_count, 0);

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Entity 360°</div>
          <h1>{entity.canonical_name}</h1>
          <div className="muted">{entity.country || "国别待核实"} · {roles.join(" / ") || "角色待积累"}</div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="primary-button" href="/knowledge/entities">返回主体列表</Link>
          <Link className="primary-button" href={`/knowledge?q=${encodeURIComponent(entity.canonical_name)}`}>检索全部相关情报</Link>
        </div>
      </header>

      <section className={styles.heroMetrics}>
        <div className={styles.heroMetric}><span>关联正式机会</span><strong>{entity.opportunities.length}</strong></div>
        <div className={styles.heroMetric}><span>经营角色</span><strong>{roles.length}</strong></div>
        <div className={styles.heroMetric}><span>支持来源计数</span><strong>{sourceCount}</strong></div>
        <div className={styles.heroMetric}><span>已知别名</span><strong>{entity.aliases.length}</strong></div>
      </section>

      <div className={styles.knowledgeGrid}>
        <section className={styles.knowledgeSection}>
          <div className={styles.sectionTitle}><h2>身份与别名</h2><span className={styles.typeBadge}>{entity.status}</span></div>
          <table className="table">
            <tbody>
              <tr><td className="muted">规范名称</td><td>{entity.canonical_name}</td></tr>
              <tr><td className="muted">国别边界</td><td>{entity.country || "待核实"}</td></tr>
              <tr><td className="muted">实体类型</td><td>{entity.entity_type}</td></tr>
              <tr><td className="muted">最近更新</td><td>{formatDate(entity.updated_at)}</td></tr>
            </tbody>
          </table>
          {entity.aliases.length ? (
            <div className={styles.matched}>
              {entity.aliases.map((alias) => (
                <span className={styles.fieldBadge} key={`${alias.alias}-${alias.source_document_id ?? "manual"}`}>
                  {alias.alias} · {Math.round(alias.confidence * 100)}%
                </span>
              ))}
            </div>
          ) : <div className={styles.empty}>暂无额外别名。</div>}
        </section>

        <section className={styles.knowledgeSection}>
          <div className={styles.sectionTitle}><h2>经营认知边界</h2><span className={styles.meta}>Evidence-first</span></div>
          <p className={styles.snippet}>
            自动归一只使用规范名/已知别名与国别兼容性；同名跨国不会自动合并。这里展示的是已由来源和正式 Opportunity 关系支撑的组织身份，不推断无证据客户关系或关键人态度。
          </p>
          {roles.length ? (
            <div className={styles.matched}>{roles.map((role) => <span className={styles.roleBadge} key={role}>{role}</span>)}</div>
          ) : null}
        </section>

        <section className={`${styles.knowledgeSection} ${styles.fullWidth}`}>
          <div className={styles.sectionTitle}><h2>关联正式机会</h2><span className={styles.meta}>{entity.opportunities.length} 个</span></div>
          {entity.opportunities.length ? (
            <div className={styles.relatedList}>
              {entity.opportunities.map((item) => (
                <article className={styles.relatedCard} key={`${item.opportunity_id}-${item.role}`}>
                  <div className={styles.cardTop}>
                    <div>
                      <Link className={styles.resultTitle} href={`/knowledge/opportunities/${encodeURIComponent(item.opportunity_id)}`}>
                        {item.title}
                      </Link>
                      <div className={styles.meta}>{item.country || "国别待核实"} · {item.sector || "专业待核实"} · {item.stage || "阶段待核实"}</div>
                    </div>
                    <span className={styles.roleBadge}>{item.role}</span>
                  </div>
                  <div className={styles.matched}>
                    <span className={styles.fieldBadge}>置信 {Math.round(item.confidence * 100)}%</span>
                    <span className={styles.fieldBadge}>支持来源 {item.source_count}</span>
                    <span className={styles.fieldBadge}>最近出现 {formatDate(item.last_seen_at)}</span>
                  </div>
                </article>
              ))}
            </div>
          ) : <div className={styles.empty}>当前尚未关联正式 Opportunity。</div>}
        </section>
      </div>
    </>
  );
}

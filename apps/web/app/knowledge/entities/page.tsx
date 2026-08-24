import Link from "next/link";

import { getEntities } from "@/lib/operating";
import styles from "../knowledge.module.css";

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function EntityIndexPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const query = first(params.q).trim();
  const entities = await getEntities(query, 200);

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Enterprise Knowledge · Entities</div>
          <h1>经营主体</h1>
          <div className="muted">查看业主、融资方、竞争对手和合作伙伴在正式经营机会中的历史出现与角色。</div>
        </div>
        <Link className="primary-button" href="/knowledge">返回经营情报</Link>
      </header>

      <section className={styles.searchPanel}>
        <form className={styles.searchForm} action="/knowledge/entities" method="get" style={{ gridTemplateColumns: "minmax(260px, 1fr) auto" }}>
          <label className={styles.field}>
            <span>主体名称</span>
            <input name="q" defaultValue={query} placeholder="业主、融资机构、竞争对手、伙伴…" />
          </label>
          <button className={styles.searchButton} type="submit">筛选</button>
        </form>

        {entities.length ? (
          <div className={styles.entityList}>
            {entities.map((entity) => (
              <article className={styles.entityCard} key={entity.id}>
                <div className={styles.cardTop}>
                  <div>
                    <Link className={styles.resultTitle} href={`/knowledge/entities/${encodeURIComponent(entity.id)}`}>
                      {entity.canonical_name}
                    </Link>
                    <div className={styles.meta}>{entity.country || "国别待核实"} · {entity.entity_type}</div>
                  </div>
                  <span className={styles.typeBadge}>{entity.opportunity_count} 个正式机会</span>
                </div>
                <div className={styles.snippet}>最近更新：{new Date(entity.updated_at).toLocaleString("zh-CN", { hour12: false })}</div>
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.empty}>当前没有匹配的经营主体。</div>
        )}
      </section>
    </>
  );
}

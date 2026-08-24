import Link from "next/link";

import {
  CandidateItem,
  SearchResponse,
  SearchResultItem,
  getKnowledgeSearch,
  getPendingCandidates,
} from "@/lib/knowledge";
import styles from "./knowledge.module.css";

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function valueOf(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function resourceLabel(type: SearchResultItem["resource_type"]): string {
  return {
    opportunity: "正式机会",
    candidate: "待审候选",
    entity: "经营主体",
    evidence: "证据事实",
    source: "正式来源",
  }[type];
}

function destination(item: SearchResultItem): string | null {
  if (item.resource_type === "opportunity") {
    return `/knowledge/opportunities/${encodeURIComponent(item.resource_id)}`;
  }
  if (item.opportunity_id) {
    return `/knowledge/opportunities/${encodeURIComponent(item.opportunity_id)}`;
  }
  if (item.resource_type === "entity") {
    return `/knowledge?q=${encodeURIComponent(item.title)}&types=entity`;
  }
  return null;
}

function SearchResults({ result }: { result: SearchResponse }) {
  if (!result.results.length) {
    return <div className={styles.empty}>没有找到匹配的经营情报资产。可尝试项目名、业主、融资方、国家或专业关键词。</div>;
  }
  return (
    <div className={styles.resultList}>
      {result.results.map((item) => {
        const href = destination(item);
        return (
          <article className={styles.resultCard} key={`${item.resource_type}-${item.resource_id}`}>
            <div className={styles.resultTop}>
              <div>
                <div className={styles.meta}>
                  <span className={styles.typeBadge}>{resourceLabel(item.resource_type)}</span> {item.subtitle}
                </div>
                {href ? (
                  <Link className={styles.resultTitle} href={href}>{item.title}</Link>
                ) : (
                  <div className={styles.resultTitle}>{item.title}</div>
                )}
              </div>
              <div className={styles.scoreBadge}>{item.relevance_score}</div>
            </div>
            {item.snippet ? <div className={styles.snippet}>{item.snippet}</div> : null}
            <div className={styles.matched}>
              {item.matched_fields.map((field) => (
                <span className={styles.fieldBadge} key={field}>命中 · {field}</span>
              ))}
            </div>
          </article>
        );
      })}
      <div className={styles.note}>{result.note}</div>
    </div>
  );
}

function CandidateCard({ item }: { item: CandidateItem }) {
  return (
    <article className={styles.candidateCard}>
      <div className={styles.cardTop}>
        <div>
          <strong>{item.discovery.title}</strong>
          <div className={styles.meta}>{item.discovery.country} · {item.discovery.sector} · {item.discovery.stage}</div>
        </div>
        <span className={styles.typeBadge}>{Math.round(item.discovery.confidence * 100)}%</span>
      </div>
      <div className={styles.snippet}>{item.discovery.summary}</div>
      <div className={styles.candidateMeta}>
        <div className={styles.metric}>来源 <strong>{item.source_count}</strong></div>
        <div className={styles.metric}>主体 <strong>{item.entities.length}</strong></div>
        <div className={styles.metric}>业主 <strong>{item.discovery.owner}</strong></div>
        <div className={styles.metric}>疑似正式机会 <strong>{item.duplicate_matches.length}</strong></div>
      </div>
      {item.entities.length ? (
        <div className={styles.matched}>
          {item.entities.slice(0, 5).map((entity) => (
            <span className={styles.roleBadge} key={entity.entity_id}>{entity.name} · {entity.roles.join("/")}</span>
          ))}
        </div>
      ) : null}
      {item.duplicate_matches.length ? (
        <div className={styles.matched}>
          {item.duplicate_matches.slice(0, 3).map((match) => (
            <Link
              className={styles.fieldBadge}
              href={`/knowledge/opportunities/${encodeURIComponent(match.opportunity_id)}`}
              key={match.opportunity_id}
            >
              疑似重复 · {match.title} · {Math.round(match.similarity * 100)}%
            </Link>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export default async function KnowledgePage({ searchParams }: PageProps) {
  const params = await searchParams;
  const query = valueOf(params.q).trim();
  const types = valueOf(params.types);
  const country = valueOf(params.country);
  const sector = valueOf(params.sector);
  const entityRole = valueOf(params.entity_role);

  const candidatePromise = getPendingCandidates(12);
  const searchPromise = query.length >= 2
    ? getKnowledgeSearch({
        query,
        types: types || undefined,
        country: country || undefined,
        sector: sector || undefined,
        entityRole: entityRole || undefined,
        limit: 40,
      })
    : Promise.resolve<SearchResponse | null>(null);

  const [candidateState, searchState] = await Promise.allSettled([candidatePromise, searchPromise]);
  const candidates = candidateState.status === "fulfilled" ? candidateState.value : [];
  const searchResult = searchState.status === "fulfilled" ? searchState.value : null;
  const error = [
    candidateState.status === "rejected" ? "候选商机读取失败" : "",
    searchState.status === "rejected" ? "知识检索失败" : "",
  ].filter(Boolean).join("；");

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Market Intelligence Workbench</div>
          <h1>经营情报工作台</h1>
          <div className="muted">统一查项目、业主、融资方、证据与来源，并把待审候选放到同一个经营入口。</div>
        </div>
      </header>

      {error ? <div className="error-box" style={{ marginBottom: 16 }}>{error}。请检查认证、API 与数据库连接。</div> : null}

      <div className={styles.workbench}>
        <section className={styles.searchPanel}>
          <form className={styles.searchForm} action="/knowledge" method="get">
            <label className={styles.field}>
              <span>关键词</span>
              <input name="q" defaultValue={query} placeholder="项目名、业主、融资方、证据关键词…" minLength={2} />
            </label>
            <label className={styles.field}>
              <span>资源类型</span>
              <select name="types" defaultValue={types}>
                <option value="">全部</option>
                <option value="opportunity">正式机会</option>
                <option value="candidate">待审候选</option>
                <option value="entity">经营主体</option>
                <option value="evidence">证据事实</option>
                <option value="source">正式来源</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>国家</span>
              <input name="country" defaultValue={country} placeholder="Nigeria" />
            </label>
            <label className={styles.field}>
              <span>主体角色</span>
              <select name="entity_role" defaultValue={entityRole}>
                <option value="">全部</option>
                <option value="owner">业主</option>
                <option value="financier">融资方</option>
                <option value="competitor">竞争对手</option>
                <option value="partner">合作伙伴</option>
              </select>
            </label>
            <button className={styles.searchButton} type="submit">检索</button>
            {sector ? <input type="hidden" name="sector" value={sector} /> : null}
          </form>

          {query.length < 2 ? (
            <div className={styles.empty}>
              输入至少 2 个字符开始检索。搜索结果会说明命中的字段，相关度只代表“检索匹配”，不会冒充经营评分。
            </div>
          ) : searchResult ? (
            <SearchResults result={searchResult} />
          ) : null}
        </section>

        <aside className={styles.sidePanel}>
          <div className={styles.sideTitle}>
            <h2>待审候选</h2>
            <span className={styles.meta}>{candidates.length} 条</span>
          </div>
          {candidates.length ? (
            <div className={styles.candidateList}>
              {candidates.map((item) => <CandidateCard item={item} key={item.id} />)}
            </div>
          ) : (
            <div className={styles.empty}>当前没有待审候选，或候选接口暂不可用。</div>
          )}
        </aside>
      </div>
    </>
  );
}

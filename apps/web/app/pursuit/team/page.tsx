import Link from "next/link";

import { getTeamWork } from "@/lib/pursuit";
import PursuitNav from "../pursuit-nav";
import styles from "../pursuit.module.css";

function dateLabel(value: string | null): string {
  if (!value) return "未设置";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}

export default async function TeamWorkPage() {
  const data = await getTeamWork();
  const blocked = data.workspaces.reduce((sum, item) => sum + item.blocked, 0);
  const open = data.workspaces.reduce((sum, item) => sum + item.open + item.in_progress, 0);
  const participants = data.workspaces.reduce((sum, item) => sum + item.participant_count, 0);

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Pursuit Orchestration · Team Work</div>
          <h1>团队经营工作</h1>
          <div className="muted">从 Workspace 维度看参与人数、未结工作、阻塞和复盘节奏，不用靠微信群追问“谁在做”。</div>
        </div>
      </header>
      <PursuitNav />

      <section className={styles.metrics}>
        <div className={styles.metric}><span>Active Workspaces</span><strong>{data.count}</strong></div>
        <div className={styles.metric}><span>未结 Work Items</span><strong>{open}</strong></div>
        <div className={styles.metric}><span>Blocked</span><strong>{blocked}</strong></div>
        <div className={styles.metric}><span>参与席位</span><strong>{participants}</strong></div>
      </section>

      {data.workspaces.length ? (
        <div className={styles.grid3}>
          {data.workspaces.map((item) => (
            <article className={styles.section} key={item.workspace_id}>
              <div className={styles.cardTop}>
                <div>
                  <Link className={styles.cardTitle} href={`/pursuit/opportunities/${encodeURIComponent(item.opportunity_id)}`}>
                    {item.title}
                  </Link>
                  <div className={styles.meta}>{item.country} · {item.sector}</div>
                </div>
                <span className={styles.priority}>{item.priority}</span>
              </div>
              <div className={styles.workCounts}>
                <div>Open<strong>{item.open}</strong></div>
                <div>进行中<strong>{item.in_progress}</strong></div>
                <div>Blocked<strong>{item.blocked}</strong></div>
                <div>Done<strong>{item.done}</strong></div>
              </div>
              <div className={styles.meta} style={{ marginTop: 12 }}>
                参与 {item.participant_count} 人 · 下次复盘 {dateLabel(item.next_review_at)}
              </div>
              <div className={styles.formActions} style={{ marginTop: 12 }}>
                <Link className={styles.linkButton} href={`/pursuit/opportunities/${encodeURIComponent(item.opportunity_id)}`}>
                  打开 Pursuit Workspace
                </Link>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className={styles.empty}>当前还没有 Active Pursuit Workspace。manager 可从正式 Opportunity 开启经营协同。</div>
      )}
    </>
  );
}

import Link from "next/link";

import { getMyWork } from "@/lib/pursuit";
import PursuitNav from "./pursuit-nav";
import styles from "./pursuit.module.css";

function dateLabel(value: string | null): string {
  if (!value) return "未设置";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

function statusClass(status: string): string {
  if (status === "blocked") return `${styles.status} ${styles.blocked}`;
  if (status === "done") return `${styles.status} ${styles.done}`;
  if (status === "in_progress") return `${styles.status} ${styles.inProgress}`;
  return `${styles.status} ${styles.open}`;
}

export default async function PursuitMyWorkPage() {
  const data = await getMyWork();
  const blocked = data.work_items.filter((item) => item.status === "blocked").length;
  const overdue = data.work_items.filter(
    (item) => item.due_at && new Date(item.due_at).getTime() < Date.now(),
  ).length;

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Pursuit Orchestration · My Work</div>
          <h1>我的经营工作</h1>
          <div className="muted">
            {data.membership
              ? `${data.membership.display_name} · ${data.membership.role} · 只显示当前账号真实绑定的 Work Item 与 Review。`
              : "当前账号尚未解析到有效 Membership。"}
          </div>
        </div>
      </header>

      <PursuitNav />

      <section className={styles.metrics}>
        <div className={styles.metric}><span>我的未结事项</span><strong>{data.work_items.length}</strong></div>
        <div className={styles.metric}><span>已阻塞</span><strong>{blocked}</strong></div>
        <div className={styles.metric}><span>已逾期</span><strong>{overdue}</strong></div>
        <div className={styles.metric}><span>待我复核</span><strong>{data.pending_reviews.length}</strong></div>
      </section>

      <div className={styles.grid2}>
        <section className={styles.section}>
          <div className={styles.sectionHead}>
            <h2>我的 Work Items</h2>
            <span className={styles.meta}>参与 {data.workspace_count} 个 Pursuit Workspace</span>
          </div>
          {data.work_items.length ? (
            <div className={styles.list}>
              {data.work_items.map((item) => (
                <article className={styles.card} key={item.id}>
                  <div className={styles.cardTop}>
                    <div>
                      {item.opportunity_id ? (
                        <Link className={styles.cardTitle} href={`/pursuit/opportunities/${encodeURIComponent(item.opportunity_id)}`}>
                          {item.title}
                        </Link>
                      ) : <strong>{item.title}</strong>}
                      <div className={styles.meta}>{item.opportunity_title} · {item.country}</div>
                    </div>
                    <span className={styles.priority}>{item.priority}</span>
                  </div>
                  <div className={styles.badges}>
                    <span className={statusClass(item.status)}>{item.status}</span>
                    <span className={styles.badge}>截止 {dateLabel(item.due_at)}</span>
                  </div>
                  {item.blocked_reason ? <div className={styles.note} style={{ marginTop: 8 }}>阻塞原因：{item.blocked_reason}</div> : null}
                </article>
              ))}
            </div>
          ) : (
            <div className={styles.empty}>当前没有分配给你的未结 Work Item。</div>
          )}
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHead}>
            <h2>待我复核</h2>
            <span className={styles.meta}>Decision Gate Review</span>
          </div>
          {data.pending_reviews.length ? (
            <div className={styles.list}>
              {data.pending_reviews.map((review) => (
                <article className={styles.card} key={review.review_id}>
                  <div className={styles.cardTop}>
                    <div>
                      <strong>{review.gate_title}</strong>
                      <div className={styles.meta}>{review.opportunity_title} · {review.country}</div>
                    </div>
                    <span className={styles.status}>pending</span>
                  </div>
                  <div className={styles.meta} style={{ marginTop: 8 }}>请求时间：{dateLabel(review.requested_at)}</div>
                  {review.opportunity_id ? (
                    <div className={styles.formActions} style={{ marginTop: 10 }}>
                      <Link className={styles.linkButton} href={`/pursuit/opportunities/${encodeURIComponent(review.opportunity_id)}`}>
                        进入 Workspace 复核
                      </Link>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <div className={styles.empty}>当前没有等待你处理的 Gate Review。</div>
          )}
        </section>
      </div>
    </>
  );
}

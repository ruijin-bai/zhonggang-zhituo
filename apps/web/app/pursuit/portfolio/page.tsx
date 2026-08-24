import Link from "next/link";

import { getPortfolio } from "@/lib/pursuit";
import PursuitNav from "../pursuit-nav";
import styles from "../pursuit.module.css";

function decisionClass(decision: string | null | undefined): string {
  if (decision === "GO") return `${styles.badge} ${styles.decisionGo}`;
  if (decision === "HOLD") return `${styles.badge} ${styles.decisionHold}`;
  if (decision === "NO_GO") return `${styles.badge} ${styles.decisionNoGo}`;
  return styles.badge;
}

export default async function PursuitPortfolioPage() {
  const data = await getPortfolio();
  const blocked = data.items.reduce((sum, item) => sum + item.blocked_work_items, 0);
  const activeWork = data.items.reduce((sum, item) => sum + item.open_work_items, 0);
  const decided = data.items.filter((item) => item.gate?.decision).length;

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Pursuit Orchestration · Portfolio</div>
          <h1>经营组合</h1>
          <div className="muted">把机会研判、协同负荷、Blocker 和最新 Decision Gate 放在同一管理视图，支持资源聚焦与经营会议。</div>
        </div>
      </header>
      <PursuitNav />

      <section className={styles.metrics}>
        <div className={styles.metric}><span>Pursuit Workspaces</span><strong>{data.count}</strong></div>
        <div className={styles.metric}><span>未结 Work Items</span><strong>{activeWork}</strong></div>
        <div className={styles.metric}><span>Blocked Items</span><strong>{blocked}</strong></div>
        <div className={styles.metric}><span>已有 Gate Decision</span><strong>{decided}</strong></div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHead}><h2>Portfolio</h2><span className={styles.meta}>Assessment ≠ Decision；两者并列展示，不互相冒充。</span></div>
        {data.items.length ? (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Opportunity</th>
                  <th>市场</th>
                  <th>研判</th>
                  <th>Workspace</th>
                  <th>工作负荷</th>
                  <th>最新 Gate</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.workspace_id}>
                    <td>
                      <Link className={styles.cardTitle} href={`/pursuit/opportunities/${encodeURIComponent(item.opportunity_id)}`}>
                        {item.title}
                      </Link>
                      <div className={styles.meta}>{item.stage}</div>
                    </td>
                    <td>{item.country}<div className={styles.meta}>{item.sector}</div></td>
                    <td>
                      <strong>{item.score}</strong> · {item.grade}
                      <div className={styles.meta}>置信度 {item.confidence}% · {item.assessment_decision}</div>
                    </td>
                    <td><span className={styles.priority}>{item.priority}</span><div className={styles.meta}>{item.workspace_status}</div></td>
                    <td>
                      未结 {item.open_work_items}
                      <div className={item.blocked_work_items ? `${styles.meta} ${styles.blocked}` : styles.meta}>Blocked {item.blocked_work_items}</div>
                    </td>
                    <td>
                      {item.gate ? (
                        <>
                          <div>{item.gate.title}</div>
                          <div className={styles.badges}>
                            <span className={styles.badge}>{item.gate.type}</span>
                            <span className={styles.status}>{item.gate.status}</span>
                            {item.gate.decision ? <span className={decisionClass(item.gate.decision)}>{item.gate.decision}</span> : null}
                          </div>
                        </>
                      ) : <span className={styles.meta}>尚未建立 Gate</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className={styles.empty}>当前还没有 Pursuit Workspace。</div>}
      </section>
    </>
  );
}

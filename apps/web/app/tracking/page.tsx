import Link from "next/link";
import { getDemoTrackingBoard } from "@/lib/demo-operating";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

async function getBoard() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/tracking`, { cache: "no-store" });
    if (!response.ok) throw new Error("tracking unavailable");
    return await response.json();
  } catch {
    return getDemoTrackingBoard();
  }
}

export default async function TrackingPage() {
  const board = await getBoard();
  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">重点经营项目</div>
          <h1>重点项目跟踪台</h1>
          <div className="muted">把“值得追”转化为持续更新的项目状态、经营行动、风险预警和复盘节奏。</div>
        </div>
      </header>

      <section className="kpi-grid">
        <div className="card"><div className="kpi-label">重点跟踪</div><div className="kpi-value">{board.watch_count}</div><div className="kpi-note">当前重点经营项目</div></div>
        <div className="card"><div className="kpi-label">待办行动</div><div className="kpi-value">{board.open_action_count}</div><div className="kpi-note">经营动作未完成</div></div>
        <div className="card"><div className="kpi-label">逾期行动</div><div className="kpi-value">{board.overdue_action_count}</div><div className="kpi-note">需要立即处理</div></div>
        <div className="card"><div className="kpi-label">未关闭预警</div><div className="kpi-value">{board.open_alert_count}</div><div className="kpi-note">证据 / 窗口 / 进度</div></div>
      </section>

      {!board.items.length ? (
        <section className="section">
          <h2>尚未建立重点跟踪清单</h2>
          <p className="muted">先从机会池选择一个重点项目加入跟踪后，这里会形成项目级经营驾驶舱。</p>
          <Link href="/opportunities"><strong>进入机会池 →</strong></Link>
        </section>
      ) : (
        <div className="stack">
          {board.items.map((item: any) => (
            <section className="section tracking-card" key={item.opportunity.id}>
              <div className="section-head">
                <div>
                  <div className="eyebrow">{item.watch?.priority === "high" ? "高优先级" : item.watch?.priority === "medium" ? "中优先级" : "建议跟踪"}</div>
                  <h2 style={{ marginTop: 6 }}>{item.opportunity.title}</h2>
                  <div className="muted">{item.opportunity.country} · {item.opportunity.sector} · {item.opportunity.stage}</div>
                </div>
                <div className="tracking-score"><strong>{item.opportunity.score}</strong><span>{item.opportunity.grade}级 / {item.opportunity.decision}</span></div>
              </div>

              <div className="tracking-grid">
                <div>
                  <div className="tracking-label">经营判断</div>
                  <p>{item.opportunity.pursuit_thesis}</p>
                  <div className="tracking-label">负责人 / 下次复盘</div>
                  <div>{item.watch?.owner ?? "未指定"} · {item.watch?.next_review_at ? new Date(item.watch.next_review_at).toLocaleDateString("zh-CN") : "未设置"}</div>
                  <div className="hero-actions"><Link href={`/opportunities/${item.opportunity.id}`}>进入项目研判</Link><Link href={`/strategy?id=${item.opportunity.id}`}>进入赢标策略</Link></div>
                </div>

                <div>
                  <div className="tracking-label">经营行动</div>
                  {item.actions.length ? item.actions.slice(0, 5).map((action: any) => (
                    <div className="tracking-row" key={action.id}>
                      <div><strong>{action.title}</strong><div className="muted small">{action.owner} · {action.due_at ? new Date(action.due_at).toLocaleDateString("zh-CN") : "无截止日期"}</div></div>
                      <span className={`badge ${action.status === "done" ? "badge-a" : ""}`}>{action.status === "done" ? "已完成" : "待办"}</span>
                    </div>
                  )) : <div className="muted">暂无经营行动。</div>}
                </div>

                <div>
                  <div className="tracking-label">系统预警</div>
                  {item.alerts.length ? item.alerts.slice(0, 4).map((alert: any) => (
                    <div className={`alert-line alert-${alert.severity}`} key={alert.id}>
                      <strong>{alert.title}</strong><div>{alert.message}</div>
                    </div>
                  )) : <div className="muted">暂无未关闭预警。</div>}
                </div>

                <div>
                  <div className="tracking-label">关键事件时间线</div>
                  <div className="timeline compact-timeline">
                    {item.timeline.length ? item.timeline.map((event: any, index: number) => (
                      <div key={`${event.type}-${index}`}><strong>{event.type === "strategy_updated" ? "策略更新" : event.type === "watch_started" ? "进入重点跟踪" : event.type}</strong><div className="muted small">{new Date(event.at).toLocaleString("zh-CN")}</div></div>
                    )) : <div className="muted">暂无事件记录。</div>}
                  </div>
                </div>
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}

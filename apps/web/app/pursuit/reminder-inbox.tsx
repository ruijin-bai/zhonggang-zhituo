"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type { PursuitReminderInbox as ReminderInboxData } from "@/lib/pursuit";
import styles from "./pursuit.module.css";

type Props = {
  data: ReminderInboxData;
  canAcknowledge: boolean;
};

function severityClass(severity: string): string {
  if (severity === "critical") return styles.blocked;
  if (severity === "high") return styles.decisionNoGo;
  if (severity === "warning") return styles.inProgress;
  return styles.open;
}

function dateTime(value: string | null): string {
  if (!value) return "未设置";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

export default function PursuitReminderInbox({ data, canAcknowledge }: Props) {
  const router = useRouter();
  const keys = useRef(new Map<string, string>());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function acknowledge(reminderId: string) {
    setBusy(reminderId);
    setError("");
    let key = keys.current.get(reminderId);
    if (!key) {
      key = `web-pursuit-reminder-${crypto.randomUUID()}`;
      keys.current.set(reminderId, key);
    }
    try {
      const response = await fetch("/api/pursuit/mutate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "acknowledge_reminder",
          reminder_id: reminderId,
          idempotency_key: key,
          payload: {},
        }),
      });
      const payload = (await response.json()) as { detail?: string };
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      keys.current.delete(reminderId);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reminder 确认失败");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className={styles.section} style={{ marginBottom: 18 }}>
      <div className={styles.sectionHead}>
        <h2>需要我处理的提醒</h2>
        <span className={styles.meta}>{data.count} 条 active / acknowledged</span>
      </div>
      <p className={styles.note}>
        Reminder 由截止时间、持续阻塞、Gate 与 Review 状态自动生成。已知悉不等于问题已解决；条件解除后系统才会自动关闭提醒。
      </p>
      {error ? <div className={styles.error} style={{ marginBottom: 10 }}>{error}</div> : null}
      {data.items.length ? (
        <div className={styles.list}>
          {data.items.map((item) => (
            <article className={styles.card} key={item.id}>
              <div className={styles.cardTop}>
                <div>
                  <Link className={styles.cardTitle} href={`/pursuit/opportunities/${encodeURIComponent(item.opportunity_id)}`}>
                    {item.title}
                  </Link>
                  <div className={styles.meta}>{item.opportunity_title} · {item.type}</div>
                </div>
                <div className={styles.badges} style={{ marginTop: 0 }}>
                  <span className={`${styles.status} ${severityClass(item.severity)}`}>{item.severity}</span>
                  {item.is_escalation ? <span className={styles.blocked}>升级到我</span> : null}
                  <span className={styles.status}>{item.status}</span>
                </div>
              </div>
              <div className={styles.note} style={{ marginTop: 8 }}>{item.message}</div>
              <div className={styles.meta} style={{ marginTop: 7 }}>
                首次触发 {dateTime(item.first_triggered_at)} · 最近触发 {dateTime(item.last_triggered_at)}
                {item.source_due_at ? ` · 业务截止 ${dateTime(item.source_due_at)}` : ""}
                {item.occurrence_count > 1 ? ` · 已发生 ${item.occurrence_count} 次` : ""}
              </div>
              <div className={styles.formActions} style={{ marginTop: 10 }}>
                <Link className={styles.linkButton} href={`/pursuit/opportunities/${encodeURIComponent(item.opportunity_id)}`}>
                  处理原事项
                </Link>
                {canAcknowledge && item.status !== "acknowledged" ? (
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    disabled={busy !== null}
                    onClick={() => acknowledge(item.id)}
                  >
                    {busy === item.id ? "正在确认…" : "已知悉"}
                  </button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className={styles.empty}>当前没有系统主动生成的执行提醒。</div>
      )}
    </section>
  );
}

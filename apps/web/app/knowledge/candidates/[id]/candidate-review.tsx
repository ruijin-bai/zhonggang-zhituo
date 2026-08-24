"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import type { CandidateItem } from "@/lib/knowledge";
import styles from "../../knowledge.module.css";

type Props = {
  candidate: CandidateItem;
  canReview: boolean;
};

type ReviewResponse = {
  detail?: string;
  opportunity?: { id: string };
  id?: string;
  status?: string;
};

export default function CandidateReview({ candidate, canReview }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function review(body: Record<string, unknown>): Promise<ReviewResponse> {
    const response = await fetch(`/api/candidates/${encodeURIComponent(candidate.id)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = (await response.json()) as ReviewResponse;
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("confirm");
    setError("");
    setMessage("");
    const data = new FormData(event.currentTarget);
    const estimatedValue = String(data.get("estimated_value_usd_m") ?? "").trim();
    const edits: Record<string, unknown> = {
      title: String(data.get("title") ?? "").trim(),
      country: String(data.get("country") ?? "").trim(),
      region: String(data.get("region") ?? "").trim(),
      sector: String(data.get("sector") ?? "").trim(),
      stage: String(data.get("stage") ?? "").trim(),
      owner: String(data.get("owner") ?? "").trim(),
      summary: String(data.get("summary") ?? "").trim(),
    };
    if (estimatedValue) edits.estimated_value_usd_m = Number(estimatedValue);

    try {
      const payload = await review({ action: "confirm", edits });
      if (payload.opportunity?.id) {
        router.push(`/knowledge/opportunities/${encodeURIComponent(payload.opportunity.id)}`);
        return;
      }
      setMessage("Candidate 已确认入池。");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认失败");
    } finally {
      setBusy(null);
    }
  }

  async function reject() {
    if (!window.confirm("确认拒绝这个 Candidate？原始来源与审计记录仍会保留。")) return;
    setBusy("reject");
    setError("");
    setMessage("");
    try {
      await review({ action: "reject" });
      router.push("/knowledge");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "拒绝失败");
    } finally {
      setBusy(null);
    }
  }

  async function attach(opportunityId: string) {
    if (!window.confirm("将这个 Candidate 的支持文档作为补充证据挂到该正式 Opportunity？")) return;
    setBusy(`attach:${opportunityId}`);
    setError("");
    setMessage("");
    try {
      await review({ action: "attach", opportunity_id: opportunityId });
      router.push(`/knowledge/opportunities/${encodeURIComponent(opportunityId)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "挂接证据失败");
    } finally {
      setBusy(null);
    }
  }

  if (!canReview) {
    return (
      <section className={styles.knowledgeSection}>
        <div className={styles.sectionTitle}><h2>人工复核</h2><span className={styles.typeBadge}>只读</span></div>
        <div className={styles.empty}>当前账号可查看 Candidate，但确认、拒绝和挂接正式证据需要 manager 或 admin 权限。</div>
      </section>
    );
  }

  if (candidate.status !== "pending") {
    return (
      <section className={styles.knowledgeSection}>
        <div className={styles.sectionTitle}><h2>人工复核</h2><span className={styles.typeBadge}>{candidate.status}</span></div>
        <div className={styles.empty}>该 Candidate 已完成审核，当前不再允许重复处理。</div>
      </section>
    );
  }

  return (
    <section className={styles.knowledgeSection}>
      <div className={styles.sectionTitle}><h2>人工复核</h2><span className={styles.typeBadge}>manager</span></div>
      <form onSubmit={confirm} style={{ display: "grid", gap: 10 }}>
        <label className={styles.field}><span>项目名称</span><input name="title" defaultValue={candidate.discovery.title} required /></label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <label className={styles.field}><span>国家</span><input name="country" defaultValue={candidate.discovery.country} required /></label>
          <label className={styles.field}><span>区域</span><input name="region" defaultValue={candidate.discovery.region} required /></label>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <label className={styles.field}><span>专业</span><input name="sector" defaultValue={candidate.discovery.sector} required /></label>
          <label className={styles.field}><span>阶段</span><input name="stage" defaultValue={candidate.discovery.stage} required /></label>
        </div>
        <label className={styles.field}><span>业主</span><input name="owner" defaultValue={candidate.discovery.owner} required /></label>
        <label className={styles.field}>
          <span>估算规模（USD M，可空）</span>
          <input name="estimated_value_usd_m" type="number" min="0" step="0.01" defaultValue={candidate.discovery.estimated_value_usd_m ?? ""} />
        </label>
        <label className={styles.field}><span>项目摘要</span><textarea name="summary" rows={6} defaultValue={candidate.discovery.summary} required /></label>

        {error ? <div className="error-box">{error}</div> : null}
        {message ? <div className={styles.note}>{message}</div> : null}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className={styles.searchButton} type="submit" disabled={busy !== null}>
            {busy === "confirm" ? "正在确认…" : "确认入正式机会池"}
          </button>
          <button
            type="button"
            disabled={busy !== null}
            onClick={reject}
            style={{ minHeight: 40, border: "1px solid #b24b4b", borderRadius: 7, padding: "0 16px", background: "#fff", color: "#8a3030", fontWeight: 700, cursor: "pointer" }}
          >
            {busy === "reject" ? "正在拒绝…" : "拒绝 Candidate"}
          </button>
        </div>
      </form>

      {candidate.duplicate_matches.length ? (
        <div style={{ marginTop: 20 }}>
          <div className={styles.sectionTitle}><h2>疑似已有正式机会</h2><span className={styles.meta}>需人工判断</span></div>
          <div className={styles.relatedList}>
            {candidate.duplicate_matches.map((match) => (
              <article className={styles.relatedCard} key={match.opportunity_id}>
                <strong>{match.title}</strong>
                <div className={styles.meta}>{match.country} · 相似度 {Math.round(match.similarity * 100)}%</div>
                <button
                  type="button"
                  className={styles.fieldBadge}
                  disabled={busy !== null}
                  onClick={() => attach(match.opportunity_id)}
                  style={{ marginTop: 8, cursor: "pointer" }}
                >
                  {busy === `attach:${match.opportunity_id}` ? "正在挂接…" : "作为补充证据挂到该项目"}
                </button>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

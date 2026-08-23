"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { runQueuedJob } from "@/lib/client-job";

type Fact = { field_name: string; value: string; score_hint: number | null; evidence_quote: string; confidence: number };
type Duplicate = { opportunity_id: string; title: string; country: string; similarity: number };
type Draft = {
  id: string;
  persisted: boolean;
  discovery: { project_detected: boolean; title: string; country: string; region: string; sector: string; stage: string; owner: string; estimated_value_usd_m: number | null; summary: string; confidence: number; facts: Fact[] };
  source_url?: string;
  source_title: string;
  duplicate_matches: Duplicate[];
};
type ScanResult = { mode: "ai" | "deterministic"; draft: Draft; note: string };
type ConfirmResult = { opportunity: { id: string; title: string; score: number; grade: string; confidence: number; decision: string }; note: string };

const demoText = `Nigeria transport authorities are preparing the Lekki Coastal Connector Road Project to improve access between industrial and port areas. The project is estimated at US$280 million. Owner: Lagos Transport Infrastructure Agency. A feasibility study has been completed and the procurement plan is being prepared. Financing discussions are under way with development finance institutions.`;

export default function DiscoveryWorkbench() {
  const [url, setUrl] = useState("");
  const [text, setText] = useState(demoText);
  const [publisher, setPublisher] = useState("公开来源示范");
  const [rank, setRank] = useState("B");
  const [result, setResult] = useState<ScanResult | null>(null);
  const [confirmed, setConfirmed] = useState<ConfirmResult | null>(null);
  const [confirmKey, setConfirmKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");

  async function scan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true); setError(""); setResult(null); setConfirmed(null); setConfirmKey("");
    try {
      const payload = {
        url: url || null,
        text: url ? null : text,
        source_title: url ? null : "西非港口连接通道项目公开信息",
        publisher,
        published_at: "2026-08-23",
        source_rank: rank,
        use_ai: true,
        is_demo: true,
      };
      const data = await runQueuedJob<ScanResult>("discovery.scan", payload);
      setResult(data);
      setConfirmKey(crypto.randomUUID());
    } catch (err) { setError(err instanceof Error ? err.message : "商机扫描失败"); }
    finally { setLoading(false); }
  }

  async function confirm() {
    if (!result) return;
    const stableKey = confirmKey || crypto.randomUUID();
    if (!confirmKey) setConfirmKey(stableKey);
    setConfirming(true); setError("");
    try {
      const response = await fetch("/api/discover/confirm", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": stableKey,
        },
        body: JSON.stringify({ draft_id: result.draft.id }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "确认入池失败");
      setConfirmed(payload);
    } catch (err) { setError(err instanceof Error ? err.message : "确认入池失败"); }
    finally { setConfirming(false); }
  }

  return (
    <div className="detail-grid">
      <form className="section stack" onSubmit={scan}>
        <div><h2>发现来源</h2><div className="muted">优先填公开网页 URL；也可以直接粘贴公告、项目新闻、融资文件等正文。</div></div>
        <label className="form-field"><span>公开网页 URL（可选）</span><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://..." /></label>
        {!url && <label className="form-field"><span>原始文本</span><textarea rows={12} value={text} onChange={(e) => setText(e.target.value)} /></label>}
        <label className="form-field"><span>发布机构</span><input value={publisher} onChange={(e) => setPublisher(e.target.value)} /></label>
        <label className="form-field"><span>来源等级</span><select value={rank} onChange={(e) => setRank(e.target.value)}><option value="S">S · 政府/多边机构/招标文件</option><option value="A">A · 业主官网/正式公告</option><option value="B">B · 权威财经/行业媒体</option><option value="C">C · 一般媒体</option><option value="D">D · 未核实来源</option></select></label>
        <button className="primary-button" disabled={loading}>{loading ? "正在识别项目…" : "扫描并生成商机草稿"}</button>
        <div className="policy-note">扫描通过异步队列执行，不会占用 API 请求进程；URL 抓取仅允许公开 http/https 地址，并拦截本机、内网和非文本资源。</div>
      </form>

      <div className="stack">
        <section className="section">
          <h2>待确认草稿</h2>
          {!result && !error && <div className="muted">扫描后会显示项目画像、识别置信度和疑似重复项目。</div>}
          {error && <div className="error-box">{error}</div>}
          {result && <div className="stack">
            <div className="flow"><strong>{result.mode === "ai" ? "AI Structured Output" : "确定性识别"}</strong> → 草稿 → 去重 → 人工确认</div>
            <div className="card" style={{ padding: 16 }}>
              <div className="eyebrow">{Math.round(result.draft.discovery.confidence * 100)}% DISCOVERY CONFIDENCE</div>
              <h2 style={{ marginTop: 8 }}>{result.draft.discovery.title}</h2>
              <div className="muted">{result.draft.discovery.country} · {result.draft.discovery.region} · {result.draft.discovery.sector}</div>
              <p>{result.draft.discovery.summary}</p>
              <table className="table"><tbody>
                <tr><td className="muted">阶段</td><td>{result.draft.discovery.stage}</td></tr>
                <tr><td className="muted">业主</td><td>{result.draft.discovery.owner}</td></tr>
                <tr><td className="muted">估算规模</td><td>{result.draft.discovery.estimated_value_usd_m ? `$${result.draft.discovery.estimated_value_usd_m}M` : "待核实"}</td></tr>
                <tr><td className="muted">草稿状态</td><td>{result.draft.persisted ? "已持久化，等待人工确认" : "仅预览；数据库未初始化"}</td></tr>
              </tbody></table>
            </div>
            <p className="muted">{result.note}</p>
            {result.draft.discovery.project_detected && !confirmed && <button className="primary-button" type="button" onClick={confirm} disabled={confirming || !result.draft.persisted}>{confirming ? "正在确认…" : "人工确认并进入机会池"}</button>}
          </div>}
        </section>

        {result?.draft.duplicate_matches.length ? <section className="section"><h2>疑似重复项目</h2>{result.draft.duplicate_matches.map((item) => <div className="evidence" key={item.opportunity_id}><strong>{item.title}</strong><div className="muted">{item.country} · 相似度 {Math.round(item.similarity * 100)}%</div></div>)}</section> : null}

        {result?.draft.discovery.facts.length ? <section className="section"><h2>来源事实</h2>{result.draft.discovery.facts.map((fact) => <div className="evidence" key={`${fact.field_name}-${fact.value}`}><div><span className="source-rank">{Math.round(fact.confidence * 100)}%</span><strong>{fact.field_name}</strong></div><div style={{ marginTop: 6 }}>{fact.value}{fact.score_hint !== null ? ` · 评分映射 ${fact.score_hint}` : ""}</div><div className="muted quote" style={{ marginTop: 6 }}>“{fact.evidence_quote}”</div></div>)}</section> : null}

        {confirmed && <section className="section hero-opportunity"><div className="eyebrow">Confirmed Opportunity</div><h2 style={{ marginTop: 8 }}>{confirmed.opportunity.title}</h2><div className="hero-score"><div className="score-big">{confirmed.opportunity.score}</div><div><span className={`badge badge-${confirmed.opportunity.grade.toLowerCase()}`}>{confirmed.opportunity.grade} 级</span><div className="muted" style={{ marginTop: 8 }}>{confirmed.opportunity.decision} · 置信度 {confirmed.opportunity.confidence}%</div></div></div><p>{confirmed.note}</p><Link href={`/opportunities/${confirmed.opportunity.id}`}><strong>进入项目详情 →</strong></Link></section>}
      </div>
    </div>
  );
}

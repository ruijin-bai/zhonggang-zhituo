"use client";

import { FormEvent, useState } from "react";

type Fact = {
  field_name: string;
  value: string;
  score_hint: number | null;
  evidence_quote: string;
  confidence: number;
};

type Result = {
  persisted: boolean;
  extraction_mode: "ai" | "deterministic";
  extraction: { summary: string; facts: Fact[] };
  score_before?: number;
  score_after?: number;
  grade_before?: string;
  grade_after?: string;
  decision_after?: string;
  applied_fields: string[];
  note: string;
};

const heroText = "The board approved the loan for the corridor project. The owner also published its procurement plan for the works. This financing approval enables the project to move into procurement preparation.";

export default function IntelligenceWorkbench() {
  const [text, setText] = useState(heroText);
  const [sourceRank, setSourceRank] = useState("S");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch("/api/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          opportunity_id: "west-africa-port-access-corridor",
          title: "融资与采购状态更新（工程化演示）",
          publisher: "权威来源示范",
          published_at: "2026-08-23",
          source_rank: sourceRank,
          text,
          use_ai: true,
          is_demo: true,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "情报处理失败");
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "情报处理失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="detail-grid">
      <form className="section stack" onSubmit={submit}>
        <div>
          <h2>来源文本</h2>
          <div className="muted">首版支持粘贴公告、新闻稿、融资机构文件摘要等文本。Demo 已预置 72 → 81 的英雄场景。</div>
        </div>
        <label className="form-field">
          <span>来源等级</span>
          <select value={sourceRank} onChange={(event) => setSourceRank(event.target.value)}>
            <option value="S">S · 政府 / 多边机构 / 正式招标文件</option>
            <option value="A">A · 业主官网 / 正式公告</option>
            <option value="B">B · 权威财经 / 行业媒体</option>
            <option value="C">C · 一般媒体</option>
            <option value="D">D · 未核实转载 / 社交来源</option>
          </select>
        </label>
        <label className="form-field">
          <span>情报正文</span>
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows={12} />
        </label>
        <button className="primary-button" type="submit" disabled={loading}>
          {loading ? "正在抽取与重评…" : "抽取事实并触发重评"}
        </button>
        <div className="policy-note">自动改分仅允许 S/A 级来源且单项抽取置信度 ≥ 80%；其他来源只进入证据链。</div>
      </form>

      <div className="stack">
        <section className="section">
          <h2>处理结果</h2>
          {!result && !error && <div className="muted">提交来源后，这里显示抽取事实、证据等级和评分变化。</div>}
          {error && <div className="error-box">{error}</div>}
          {result && (
            <div className="stack">
              <div className="flow"><strong>{result.extraction_mode === "ai" ? "AI Structured Output" : "确定性规则"}</strong> → Evidence → Scoring → Snapshot</div>
              <p>{result.extraction.summary}</p>
              {result.score_before !== undefined && result.score_after !== undefined && (
                <div className="score-change-box">
                  <div><span>重评前</span><strong>{result.score_before} / {result.grade_before}</strong></div>
                  <div className="change-arrow">→</div>
                  <div><span>重评后</span><strong>{result.score_after} / {result.grade_after}</strong></div>
                </div>
              )}
              <div><strong>系统说明</strong><p className="muted">{result.note}</p></div>
            </div>
          )}
        </section>

        {result?.extraction.facts.length ? (
          <section className="section">
            <h2>抽取事实与证据</h2>
            {result.extraction.facts.map((fact) => (
              <div className="evidence" key={`${fact.field_name}-${fact.value}`}>
                <div><span className="source-rank">{Math.round(fact.confidence * 100)}% 置信</span><strong>{fact.field_name}</strong></div>
                <div style={{ marginTop: 7 }}>{fact.value}{fact.score_hint !== null ? ` · 建议分 ${fact.score_hint}` : ""}</div>
                <div className="muted quote" style={{ marginTop: 7 }}>“{fact.evidence_quote}”</div>
              </div>
            ))}
          </section>
        ) : null}
      </div>
    </div>
  );
}

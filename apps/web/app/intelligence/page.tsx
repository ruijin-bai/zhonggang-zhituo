import IntelligenceWorkbench from "./workbench";

export default function IntelligencePage() {
  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Evidence Ingestion</div>
          <h1>市场情报导入与重评</h1>
          <div className="muted">把一段公开来源文本转化为结构化事实、证据与可解释评分变化。</div>
        </div>
      </header>
      <IntelligenceWorkbench />
    </>
  );
}

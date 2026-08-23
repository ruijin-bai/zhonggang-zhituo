import DiscoveryWorkbench from "./workbench";

export default function DiscoverPage() {
  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Opportunity Discovery</div>
          <h1>AI 主动发现商机</h1>
          <div className="muted">输入公开网页 URL 或原始文本，先形成待确认草稿，再由人工决定是否进入正式机会池。</div>
        </div>
      </header>
      <DiscoveryWorkbench />
    </>
  );
}

/**
 * Visible warning shown whenever a page is rendering built-in demo samples instead of live
 * business data. Never render demo content without this banner — a fallback that looks
 * identical to real data is indistinguishable from a mock-up to a reviewer.
 */
export default function DemoDataBanner({ scope }: { scope: string }) {
  return (
    <div className="demo-banner" role="alert" aria-live="polite">
      <span className="demo-banner-tag">演示数据</span>
      <span>
        当前「{scope}」展示的是内置演示样例，不是实时业务数据。请检查后端服务与数据库连接后重试。
      </span>
    </div>
  );
}

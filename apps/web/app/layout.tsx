import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

// Zhituo is an authenticated, tenant-scoped operating workspace. Server-side data access
// forwards request identity/organization headers to the API, so rendering must happen at
// request time rather than during static prerendering.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "中港智拓｜海外工程经营智能中枢",
  description: "海外工程经营操作系统的一层智能中枢",
};

// Sidebar navigation grouped by workflow stage. Each label pairs the Chinese operating
// term with the English system term so bilingual reviewers can map the UI back to the
// domain model (Candidate/Evidence/WorkItem/...). The 重点跟踪 legacy route was
// retired — its functionality is now folded into 经营协同 → 经营组合.
const NAV_GROUPS: { title: string; items: { href: string; label: string; hint?: string }[] }[] = [
  {
    title: "总览",
    items: [
      { href: "/", label: "经营总览", hint: "OVERVIEW" },
      { href: "/radar", label: "市场雷达", hint: "RADAR" },
    ],
  },
  {
    title: "机会",
    items: [
      { href: "/discover", label: "商机发现", hint: "DISCOVER" },
      { href: "/opportunities", label: "机会池", hint: "OPPORTUNITIES" },
      { href: "/knowledge", label: "经营情报", hint: "INTELLIGENCE" },
      { href: "/intelligence", label: "情报重评", hint: "RESCORE" },
    ],
  },
  {
    title: "经营",
    items: [
      { href: "/pursuit", label: "经营协同", hint: "PURSUIT" },
      { href: "/strategy", label: "赢标策略", hint: "STRATEGY" },
      { href: "/battlecard", label: "经营作战卡", hint: "BATTLECARD" },
    ],
  },
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <div className="brand-mark">智</div>
              <div>
                <strong>中港智拓</strong>
                <span>ZHITUO</span>
              </div>
            </div>
            <nav className="nav-groups">
              {NAV_GROUPS.map((group) => (
                <div className="nav-group" key={group.title}>
                  <div className="nav-group-title">{group.title}</div>
                  {group.items.map((item) => (
                    <Link href={item.href} key={item.href}>
                      <span>{item.label}</span>
                      {item.hint ? <em>{item.hint}</em> : null}
                    </Link>
                  ))}
                </div>
              ))}
            </nav>
            <div className="sidebar-foot">感知 · 判断 · 协同 · 记忆 · 学习</div>
          </aside>
          <main className="main-content">{children}</main>
        </div>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "中港智拓｜海外工程市场机会智能研判",
  description: "海外工程市场机会发现与战略经营智能体",
};

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
            <nav>
              <Link href="/">经营总览</Link>
              <Link href="/opportunities">机会池</Link>
              <Link href="/intelligence">情报导入</Link>
              <span className="nav-disabled">市场雷达 · 即将接入</span>
              <span className="nav-disabled">重点跟踪 · 即将接入</span>
            </nav>
            <div className="sidebar-foot">去哪里 · 追什么 · 怎么拿</div>
          </aside>
          <main className="main-content">{children}</main>
        </div>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "中港智拓｜海外工程经营智能中枢",
  description: "海外工程经营操作系统的一层智能中枢",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <div className="brand-mark">智</div>
              <div><strong>中港智拓</strong><span>ZHITUO</span></div>
            </div>
            <nav>
              <Link href="/">经营总览</Link>
              <Link href="/radar">市场雷达</Link>
              <Link href="/discover">商机发现</Link>
              <Link href="/knowledge">经营情报</Link>
              <Link href="/intelligence">情报重评</Link>
              <Link href="/opportunities">机会池</Link>
              <Link href="/pursuit">经营协同</Link>
              <Link href="/tracking">重点跟踪 · Legacy</Link>
              <Link href="/strategy">赢标策略</Link>
              <Link href="/battlecard">经营作战卡</Link>
            </nav>
            <div className="sidebar-foot">感知 · 判断 · 协同 · 记忆 · 学习</div>
          </aside>
          <main className="main-content">{children}</main>
        </div>
      </body>
    </html>
  );
}

import Link from "next/link";

import styles from "./pursuit.module.css";

export default function PursuitNav() {
  return (
    <nav className={styles.tabs} aria-label="Pursuit 工作台导航">
      <Link href="/pursuit">我的工作</Link>
      <Link href="/pursuit/team">团队工作</Link>
      <Link href="/pursuit/portfolio">经营组合</Link>
    </nav>
  );
}

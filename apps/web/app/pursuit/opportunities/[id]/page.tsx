import Link from "next/link";
import { notFound } from "next/navigation";

import { getOpportunityKnowledge } from "@/lib/knowledge";
import { getMyWork, getPursuitMembers, getPursuitWorkspace } from "@/lib/pursuit";
import { canEditPursuit, canManagePursuit, getSessionMeta } from "@/lib/session";
import PursuitNav from "../../pursuit-nav";
import styles from "../../pursuit.module.css";
import { OpenWorkspaceControl, WorkspaceControls } from "./workspace-controls";

function dateLabel(value: string | null): string {
  if (!value) return "未设置";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

export default async function PursuitWorkspacePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let knowledge;
  try {
    knowledge = await getOpportunityKnowledge(id);
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("404")) notFound();
    throw error;
  }

  const [session, members, myWork] = await Promise.all([
    getSessionMeta(),
    getPursuitMembers(),
    getMyWork(),
  ]);

  let workspace = null;
  try {
    workspace = await getPursuitWorkspace(id);
  } catch (error) {
    if (!(error instanceof Error) || !error.message.startsWith("404")) throw error;
  }

  const opportunity = knowledge.opportunity;
  const canEdit = canEditPursuit(session.role);
  const canManage = canManagePursuit(session.role);

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Pursuit Orchestration · Opportunity Execution</div>
          <h1>{opportunity.title}</h1>
          <div className="muted">{opportunity.country} · {opportunity.sector} · {opportunity.stage}</div>
        </div>
        <div className={styles.workspaceActions}>
          <Link className={styles.linkButton} href={`/knowledge/opportunities/${encodeURIComponent(id)}`}>查看 360° 情报</Link>
          <Link className={styles.linkButton} href={`/opportunities/${encodeURIComponent(id)}`}>查看机会研判</Link>
        </div>
      </header>
      <PursuitNav />

      <section className={styles.metrics}>
        <div className={styles.metric}><span>机会评分</span><strong>{opportunity.score}</strong></div>
        <div className={styles.metric}><span>Grade</span><strong>{opportunity.grade}</strong></div>
        <div className={styles.metric}><span>研判置信度</span><strong>{opportunity.confidence}%</strong></div>
        <div className={styles.metric}><span>Assessment</span><strong>{opportunity.decision}</strong></div>
      </section>

      {workspace ? (
        <>
          <section className={styles.workspaceHeader}>
            <div className={styles.workspaceTop}>
              <div>
                <div className="eyebrow">Canonical Pursuit Workspace</div>
                <h2 className={styles.workspaceTitle}>团队执行状态：{workspace.status}</h2>
                <div className={styles.note}>{workspace.rationale || "尚未填写经营立项理由。"}</div>
              </div>
              <div className={styles.badges}>
                <span className={styles.priority}>{workspace.priority}</span>
                <span className={styles.status}>Lead · {workspace.lead?.display_name ?? "未指定"}</span>
              </div>
            </div>
            <div className={styles.meta} style={{ marginTop: 12 }}>
              Workspace {workspace.id} · 下次复盘 {dateLabel(workspace.next_review_at)} · 当前角色 {session.role}
            </div>
          </section>

          <WorkspaceControls
            workspace={workspace}
            members={members}
            currentMembershipId={myWork.membership?.membership_id ?? null}
            canEdit={canEdit}
            canManage={canManage}
          />
        </>
      ) : (
        <OpenWorkspaceControl opportunityId={id} canManage={canManage} />
      )}
    </>
  );
}

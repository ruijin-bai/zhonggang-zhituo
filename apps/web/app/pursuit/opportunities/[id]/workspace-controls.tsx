"use client";

import { FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type { PursuitGate, PursuitMember, PursuitWorkItem, PursuitWorkspace } from "@/lib/pursuit";
import styles from "../../pursuit.module.css";

type MutationAction =
  | "open_workspace"
  | "upsert_participant"
  | "create_work_item"
  | "update_work_item"
  | "open_gate"
  | "request_review"
  | "submit_review"
  | "record_decision";

type MutationRequest = {
  action: MutationAction;
  opportunity_id?: string;
  workspace_id?: string;
  work_item_id?: string;
  gate_id?: string;
  review_id?: string;
  payload?: Record<string, unknown>;
};

type MutationResponse = { detail?: string } & Record<string, unknown>;

function isoFromLocal(value: FormDataEntryValue | null): string | null {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) throw new Error("日期时间格式无效");
  return date.toISOString();
}

function localDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function memberLabel(member: PursuitMember): string {
  return `${member.display_name} · ${member.role}`;
}

function statusClass(status: string): string {
  if (status === "blocked") return styles.blocked;
  if (status === "done") return styles.done;
  if (status === "in_progress") return styles.inProgress;
  return styles.open;
}

function decisionClass(value: string): string {
  if (value === "GO") return styles.decisionGo;
  if (value === "NO_GO") return styles.decisionNoGo;
  return styles.decisionHold;
}

function usePursuitMutation() {
  const router = useRouter();
  const keyCache = useRef(new Map<string, string>());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function mutate(label: string, request: MutationRequest): Promise<MutationResponse> {
    setBusy(label);
    setError("");
    setSuccess("");
    const fingerprint = JSON.stringify(request);
    let key = keyCache.current.get(fingerprint);
    if (!key) {
      key = `web-pursuit-${crypto.randomUUID()}`;
      keyCache.current.set(fingerprint, key);
    }
    try {
      const response = await fetch("/api/pursuit/mutate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...request, idempotency_key: key }),
      });
      const payload = (await response.json()) as MutationResponse;
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      keyCache.current.delete(fingerprint);
      setSuccess("已保存。系统已记录业务审计与 Opportunity Event。");
      router.refresh();
      return payload;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pursuit 操作失败");
      throw err;
    } finally {
      setBusy(null);
    }
  }

  return { mutate, busy, error, success };
}

export function OpenWorkspaceControl({ opportunityId, canManage }: { opportunityId: string; canManage: boolean }) {
  const { mutate, busy, error, success } = usePursuitMutation();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      await mutate("open_workspace", {
        action: "open_workspace",
        opportunity_id: opportunityId,
        payload: {
          priority: String(data.get("priority") ?? "medium"),
          rationale: String(data.get("rationale") ?? "").trim(),
          next_review_at: isoFromLocal(data.get("next_review_at")),
        },
      });
    } catch {
      // Error is rendered below; the same idempotency key is retained for a user retry.
    }
  }

  if (!canManage) {
    return (
      <section className={styles.section}>
        <div className={styles.sectionHead}><h2>Pursuit Workspace 尚未开启</h2><span className={styles.status}>只读</span></div>
        <div className={styles.empty}>当前 Opportunity 还没有正式经营协同空间。开启 Workspace 需要 manager 或 admin 权限。</div>
      </section>
    );
  }

  return (
    <section className={styles.section}>
      <div className={styles.sectionHead}><h2>开启 Pursuit Workspace</h2><span className={styles.status}>manager</span></div>
      <p className={styles.note}>显式开启后，项目才进入团队执行体系。系统不会因为浏览 Opportunity 自动创建协同状态。</p>
      <form className={styles.form} onSubmit={submit}>
        <div className={styles.formGrid2}>
          <label className={styles.field}><span>经营优先级</span><select name="priority" defaultValue="high"><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
          <label className={styles.field}><span>下次复盘</span><input name="next_review_at" type="datetime-local" /></label>
        </div>
        <label className={styles.field}><span>立项理由 / 经营目标</span><textarea name="rationale" rows={4} placeholder="为什么现在值得投入团队资源？当前最需要验证什么？" /></label>
        {error ? <div className={styles.error}>{error}</div> : null}
        {success ? <div className={styles.success}>{success}</div> : null}
        <div className={styles.formActions}><button className={styles.primaryButton} type="submit" disabled={busy !== null}>{busy ? "正在开启…" : "正式开启经营协同"}</button></div>
      </form>
    </section>
  );
}

function ParticipantForm({ workspace, members, busy, mutate }: { workspace: PursuitWorkspace; members: PursuitMember[]; busy: string | null; mutate: (label: string, request: MutationRequest) => Promise<MutationResponse> }) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      await mutate("participant", {
        action: "upsert_participant",
        workspace_id: workspace.id,
        payload: {
          membership_id: Number(data.get("membership_id")),
          participant_role: String(data.get("participant_role") ?? "contributor"),
          responsibility: String(data.get("responsibility") ?? "").trim(),
        },
      });
    } catch {}
  }
  return (
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.formGrid2}>
        <label className={styles.field}><span>成员</span><select name="membership_id" required defaultValue=""><option value="" disabled>选择组织成员</option>{members.map((member) => <option value={member.membership_id} key={member.membership_id}>{memberLabel(member)}</option>)}</select></label>
        <label className={styles.field}><span>角色</span><select name="participant_role" defaultValue="contributor"><option value="lead">Lead</option><option value="contributor">Contributor</option><option value="reviewer">Reviewer</option><option value="watcher">Watcher</option></select></label>
      </div>
      <label className={styles.field}><span>职责</span><input name="responsibility" placeholder="如：融资路径核实、技术方案牵头" /></label>
      <button className={styles.secondaryButton} type="submit" disabled={busy !== null}>添加 / 更新参与人</button>
    </form>
  );
}

function CreateWorkItemForm({ workspace, members, busy, mutate }: { workspace: PursuitWorkspace; members: PursuitMember[]; busy: string | null; mutate: (label: string, request: MutationRequest) => Promise<MutationResponse> }) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const assignee = String(data.get("assignee_membership_id") ?? "").trim();
    const dependency = String(data.get("dependency_work_item_id") ?? "").trim();
    try {
      await mutate("create_work_item", {
        action: "create_work_item",
        workspace_id: workspace.id,
        payload: {
          title: String(data.get("title") ?? "").trim(),
          description: String(data.get("description") ?? "").trim(),
          work_type: String(data.get("work_type") ?? "action"),
          assignee_membership_id: assignee ? Number(assignee) : null,
          priority: String(data.get("priority") ?? "medium"),
          due_at: isoFromLocal(data.get("due_at")),
          dependency_work_item_id: dependency || null,
        },
      });
      form.reset();
    } catch {}
  }
  const dependencies = workspace.work_items.filter((item) => item.status !== "cancelled");
  return (
    <form className={styles.form} onSubmit={submit}>
      <label className={styles.field}><span>工作项</span><input name="title" minLength={2} required placeholder="必须形成一个可验证的交付结果" /></label>
      <label className={styles.field}><span>说明</span><textarea name="description" rows={3} placeholder="完成定义、依赖事实或交付要求" /></label>
      <div className={styles.formGrid2}>
        <label className={styles.field}><span>类型</span><select name="work_type" defaultValue="action"><option value="action">Action</option><option value="milestone">Milestone</option><option value="request">Request</option></select></label>
        <label className={styles.field}><span>负责人</span><select name="assignee_membership_id" defaultValue=""><option value="">暂不指派</option>{members.map((member) => <option value={member.membership_id} key={member.membership_id}>{memberLabel(member)}</option>)}</select></label>
        <label className={styles.field}><span>优先级</span><select name="priority" defaultValue="high"><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
        <label className={styles.field}><span>截止时间</span><input name="due_at" type="datetime-local" /></label>
      </div>
      <label className={styles.field}><span>依赖工作项</span><select name="dependency_work_item_id" defaultValue=""><option value="">无依赖</option>{dependencies.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
      <button className={styles.primaryButton} type="submit" disabled={busy !== null}>创建 Work Item</button>
    </form>
  );
}

function WorkItemEditor({ item, workspace, members, busy, mutate }: { item: PursuitWorkItem; workspace: PursuitWorkspace; members: PursuitMember[]; busy: string | null; mutate: (label: string, request: MutationRequest) => Promise<MutationResponse> }) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const assignee = String(data.get("assignee_membership_id") ?? "").trim();
    const dependency = String(data.get("dependency_work_item_id") ?? "").trim();
    try {
      await mutate(`work:${item.id}`, {
        action: "update_work_item",
        work_item_id: item.id,
        payload: {
          title: String(data.get("title") ?? "").trim(),
          description: String(data.get("description") ?? "").trim(),
          assignee_membership_id: assignee ? Number(assignee) : null,
          clear_assignee: !assignee,
          status: String(data.get("status") ?? item.status),
          priority: String(data.get("priority") ?? item.priority),
          due_at: isoFromLocal(data.get("due_at")),
          clear_due_at: !String(data.get("due_at") ?? "").trim(),
          blocked_reason: String(data.get("blocked_reason") ?? "").trim(),
          dependency_work_item_id: dependency || null,
          clear_dependency: !dependency,
        },
      });
    } catch {}
  }
  const dependencies = workspace.work_items.filter((candidate) => candidate.id !== item.id && candidate.status !== "cancelled");
  return (
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.cardTop}>
        <div><span className={`${styles.status} ${statusClass(item.status)}`}>{item.status}</span> <span className={styles.priority}>{item.priority}</span></div>
        <span className={styles.meta}>{item.work_type}</span>
      </div>
      <label className={styles.field}><span>标题</span><input name="title" minLength={2} defaultValue={item.title} required /></label>
      <label className={styles.field}><span>说明</span><textarea name="description" rows={2} defaultValue={item.description} /></label>
      <div className={styles.formGrid2}>
        <label className={styles.field}><span>状态</span><select name="status" defaultValue={item.status}><option value="open">Open</option><option value="in_progress">In Progress</option><option value="blocked">Blocked</option><option value="done">Done</option><option value="cancelled">Cancelled</option></select></label>
        <label className={styles.field}><span>负责人</span><select name="assignee_membership_id" defaultValue={item.assignee?.membership_id ?? ""}><option value="">未指派</option>{members.map((member) => <option value={member.membership_id} key={member.membership_id}>{memberLabel(member)}</option>)}</select></label>
        <label className={styles.field}><span>优先级</span><select name="priority" defaultValue={item.priority}><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
        <label className={styles.field}><span>截止时间</span><input name="due_at" type="datetime-local" defaultValue={localDateTime(item.due_at)} /></label>
      </div>
      <label className={styles.field}><span>依赖</span><select name="dependency_work_item_id" defaultValue={item.dependency_work_item_id ?? ""}><option value="">无依赖</option>{dependencies.map((candidate) => <option value={candidate.id} key={candidate.id}>{candidate.title}</option>)}</select></label>
      <label className={styles.field}><span>Blocked 原因</span><input name="blocked_reason" defaultValue={item.blocked_reason ?? ""} placeholder="只有标记 Blocked 时必填" /></label>
      {item.legacy_owner_text && !item.assignee ? <div className={styles.meta}>历史负责人文本：{item.legacy_owner_text}（尚未映射为真实 Membership）</div> : null}
      <button className={styles.secondaryButton} type="submit" disabled={busy !== null}>保存 Work Item</button>
    </form>
  );
}

function GateControls({ gate, members, currentMembershipId, canEdit, canManage, busy, mutate }: { gate: PursuitGate; members: PursuitMember[]; currentMembershipId: number | null; canEdit: boolean; canManage: boolean; busy: string | null; mutate: (label: string, request: MutationRequest) => Promise<MutationResponse> }) {
  async function requestReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try { await mutate(`review-request:${gate.id}`, { action: "request_review", gate_id: gate.id, payload: { reviewer_membership_id: Number(data.get("reviewer_membership_id")) } }); } catch {}
  }
  async function submitReview(event: FormEvent<HTMLFormElement>, reviewId: string) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try { await mutate(`review:${reviewId}`, { action: "submit_review", review_id: reviewId, payload: { status: String(data.get("status") ?? "approved"), note: String(data.get("note") ?? "").trim() } }); } catch {}
  }
  async function decide(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const decision = String(data.get("decision") ?? "HOLD");
    if (!window.confirm(`确认记录 ${decision} 决策？该记录不会覆盖历史 Decision，而是形成新的 lineage。`)) return;
    try { await mutate(`decision:${gate.id}`, { action: "record_decision", gate_id: gate.id, payload: { decision, rationale: String(data.get("rationale") ?? "").trim() } }); } catch {}
  }
  const latest = gate.decisions[0] ?? null;
  return (
    <article className={styles.card}>
      <div className={styles.cardTop}>
        <div><strong>{gate.title}</strong><div className={styles.meta}>{gate.gate_type} · {gate.status}</div></div>
        {latest ? <span className={`${styles.badge} ${decisionClass(latest.decision)}`}>{latest.decision}</span> : <span className={styles.status}>待决策</span>}
      </div>
      {gate.reviews.length ? <div className={styles.list} style={{ marginTop: 12 }}>{gate.reviews.map((review) => {
        const allowed = canEdit && (canManage || review.reviewer?.membership_id === currentMembershipId);
        return <div className={styles.card} key={review.id}><div className={styles.cardTop}><strong>{review.reviewer?.display_name ?? "未知 Reviewer"}</strong><span className={styles.status}>{review.status}</span></div><div className={styles.meta}>{review.note || "尚无复核意见"}</div>{allowed ? <form className={styles.form} style={{ marginTop: 8 }} onSubmit={(event) => submitReview(event, review.id)}><div className={styles.formGrid2}><label className={styles.field}><span>Review 结果</span><select name="status" defaultValue={review.status === "pending" ? "approved" : review.status}><option value="approved">Approved</option><option value="changes_requested">Changes Requested</option><option value="waived">Waived</option></select></label><label className={styles.field}><span>意见</span><input name="note" defaultValue={review.note} /></label></div><button className={styles.secondaryButton} disabled={busy !== null}>提交 Review</button></form> : null}</div>;
      })}</div> : <div className={styles.meta} style={{ marginTop: 10 }}>尚未请求 Reviewer。</div>}
      {canManage ? <><form className={styles.form} style={{ marginTop: 12 }} onSubmit={requestReview}><div className={styles.formGrid2}><label className={styles.field}><span>新增 Reviewer</span><select name="reviewer_membership_id" required defaultValue=""><option value="" disabled>选择 Reviewer</option>{members.map((member) => <option value={member.membership_id} key={member.membership_id}>{memberLabel(member)}</option>)}</select></label><div className={styles.formActions} style={{ alignItems: "end" }}><button className={styles.secondaryButton} disabled={busy !== null}>请求 Review</button></div></div></form><form className={styles.form} style={{ marginTop: 12 }} onSubmit={decide}><div className={styles.formGrid2}><label className={styles.field}><span>Decision</span><select name="decision" defaultValue="HOLD"><option value="GO">GO</option><option value="HOLD">HOLD</option><option value="NO_GO">NO-GO</option></select></label><label className={styles.field}><span>决策理由</span><input name="rationale" minLength={2} required placeholder="基于哪些事实继续、暂停或退出？" /></label></div><button className={styles.primaryButton} disabled={busy !== null}>记录 Decision</button></form></> : null}
      {gate.decisions.length ? <div className={styles.timeline} style={{ marginTop: 14 }}>{gate.decisions.map((decision) => <div className={styles.timelineItem} key={decision.id}><strong className={decisionClass(decision.decision)} style={{ padding: "2px 7px", borderRadius: 999 }}>{decision.decision}</strong><div className={styles.note}>{decision.rationale}</div><div className={styles.meta}>{decision.decided_by?.display_name ?? "未知决策人"} · {new Date(decision.decided_at).toLocaleString("zh-CN", { hour12: false })}{decision.supersedes_decision_id ? ` · supersedes ${decision.supersedes_decision_id}` : ""}</div></div>)}</div> : null}
    </article>
  );
}

export function WorkspaceControls({ workspace, members, currentMembershipId, canEdit, canManage }: { workspace: PursuitWorkspace; members: PursuitMember[]; currentMembershipId: number | null; canEdit: boolean; canManage: boolean }) {
  const { mutate, busy, error, success } = usePursuitMutation();

  async function openGate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      await mutate("open_gate", { action: "open_gate", workspace_id: workspace.id, payload: { gate_type: String(data.get("gate_type") ?? "pursuit"), title: String(data.get("title") ?? "").trim(), due_at: isoFromLocal(data.get("due_at")) } });
      form.reset();
    } catch {}
  }

  return (
    <>
      {error ? <div className={styles.error} style={{ marginBottom: 14 }}>{error}</div> : null}
      {success ? <div className={styles.success} style={{ marginBottom: 14 }}>{success}</div> : null}
      <div className={styles.split}>
        <div style={{ display: "grid", gap: 18 }}>
          <section className={styles.section}>
            <div className={styles.sectionHead}><h2>Work Items</h2><span className={styles.meta}>{workspace.work_items.length} 项</span></div>
            {canEdit ? <CreateWorkItemForm workspace={workspace} members={members} busy={busy} mutate={mutate} /> : null}
            <div className={styles.list} style={{ marginTop: canEdit ? 18 : 0 }}>
              {workspace.work_items.length ? workspace.work_items.map((item) => <div className={styles.card} key={item.id}>{canEdit ? <WorkItemEditor item={item} workspace={workspace} members={members} busy={busy} mutate={mutate} /> : <><div className={styles.cardTop}><strong>{item.title}</strong><span className={`${styles.status} ${statusClass(item.status)}`}>{item.status}</span></div><div className={styles.note}>{item.description}</div><div className={styles.meta}>{item.assignee?.display_name ?? item.legacy_owner_text ?? "未指派"} · {item.priority}</div>{item.blocked_reason ? <div className={styles.error} style={{ marginTop: 8 }}>Blocked：{item.blocked_reason}</div> : null}</>}</div>) : <div className={styles.empty}>暂无 Work Item。</div>}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHead}><h2>Decision Gates</h2><span className={styles.meta}>{workspace.gates.length} 个</span></div>
            {workspace.gates.length ? <div className={styles.list}>{workspace.gates.map((gate) => <GateControls gate={gate} members={members} currentMembershipId={currentMembershipId} canEdit={canEdit} canManage={canManage} busy={busy} mutate={mutate} key={gate.id} />)}</div> : <div className={styles.empty}>尚未建立决策 Gate。</div>}
          </section>
        </div>

        <aside className={styles.sticky}>
          <section className={styles.section}>
            <div className={styles.sectionHead}><h3>团队与职责</h3><span className={styles.meta}>{workspace.participants.length} 人</span></div>
            <div className={styles.list}>{workspace.participants.map((participant) => <div className={styles.card} key={participant.id}><strong>{participant.member?.display_name ?? "未知成员"}</strong><div className={styles.meta}>{participant.participant_role} · {participant.member?.role ?? ""}</div><div className={styles.note}>{participant.responsibility || "未填写职责"}</div></div>)}</div>
            {canManage ? <div style={{ marginTop: 14 }}><ParticipantForm workspace={workspace} members={members} busy={busy} mutate={mutate} /></div> : null}
          </section>

          {canManage ? <section className={styles.section}><div className={styles.sectionHead}><h3>开启 Decision Gate</h3><span className={styles.status}>manager</span></div><form className={styles.form} onSubmit={openGate}><label className={styles.field}><span>Gate 类型</span><select name="gate_type" defaultValue="pursuit"><option value="qualification">Qualification</option><option value="pursuit">Pursuit</option><option value="bid">Bid</option><option value="submission">Submission</option><option value="closeout">Closeout</option></select></label><label className={styles.field}><span>标题</span><input name="title" minLength={2} required placeholder="例如：正式投标 Go/No-Go" /></label><label className={styles.field}><span>计划决策时间</span><input name="due_at" type="datetime-local" /></label><button className={styles.primaryButton} disabled={busy !== null}>开启 Gate</button></form></section> : null}
        </aside>
      </div>
    </>
  );
}

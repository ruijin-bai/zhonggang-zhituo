import "server-only";

import { serverApiFetch } from "./server-api";

export type PursuitMember = {
  membership_id: number;
  user_id: string;
  display_name: string;
  email: string;
  role: string;
  active?: boolean;
};

export type PursuitWorkItem = {
  id: string;
  work_type: string;
  title: string;
  description: string;
  assignee: PursuitMember | null;
  legacy_owner_text: string | null;
  status: "open" | "in_progress" | "blocked" | "done" | "cancelled" | string;
  priority: string;
  due_at: string | null;
  blocked_reason: string | null;
  dependency_work_item_id: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PursuitGateReview = {
  id: string;
  reviewer: PursuitMember | null;
  status: string;
  note: string;
  requested_at: string;
  reviewed_at: string | null;
};

export type PursuitDecision = {
  id: string;
  decision: "GO" | "HOLD" | "NO_GO" | string;
  rationale: string;
  decided_by: PursuitMember | null;
  supersedes_decision_id: string | null;
  decided_at: string;
};

export type PursuitGate = {
  id: string;
  gate_type: string;
  title: string;
  status: string;
  due_at: string | null;
  opened_at: string;
  closed_at: string | null;
  reviews: PursuitGateReview[];
  decisions: PursuitDecision[];
};

export type PursuitWorkspace = {
  id: string;
  status: string;
  priority: string;
  rationale: string;
  next_review_at: string | null;
  lead: PursuitMember | null;
  opportunity: {
    id: string;
    title: string;
    country: string;
    sector: string;
    stage: string;
    score: number;
    grade: string;
    confidence: number;
    decision: string;
  };
  participants: Array<{
    id: number;
    member: PursuitMember | null;
    participant_role: string;
    responsibility: string;
    status: string;
  }>;
  work_items: PursuitWorkItem[];
  gates: PursuitGate[];
  created_at: string;
  updated_at: string;
};

export type MyWork = {
  membership: PursuitMember | null;
  work_items: Array<{
    workspace_id: string;
    opportunity_id: string | null;
    opportunity_title: string;
    country: string;
    id: string;
    title: string;
    status: string;
    priority: string;
    due_at: string | null;
    blocked_reason: string | null;
  }>;
  pending_reviews: Array<{
    workspace_id: string;
    opportunity_id: string | null;
    opportunity_title: string;
    country: string;
    review_id: string;
    gate_id: string;
    gate_title: string;
    requested_at: string;
  }>;
  workspace_count: number;
};

export type TeamWork = {
  count: number;
  workspaces: Array<{
    workspace_id: string;
    opportunity_id: string;
    title: string;
    country: string;
    sector: string;
    priority: string;
    participant_count: number;
    open: number;
    in_progress: number;
    blocked: number;
    done: number;
    next_review_at: string | null;
  }>;
};

export type Portfolio = {
  count: number;
  items: Array<{
    workspace_id: string;
    opportunity_id: string;
    title: string;
    country: string;
    sector: string;
    stage: string;
    workspace_status: string;
    priority: string;
    score: number;
    grade: string;
    confidence: number;
    assessment_decision: string;
    open_work_items: number;
    blocked_work_items: number;
    gate: null | {
      id: string;
      type: string;
      title: string;
      status: string;
      decision: string | null;
    };
  }>;
};

async function readJson<T>(path: string): Promise<T> {
  const response = await serverApiFetch(path, { cache: "no-store" });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // Keep HTTP status when the backend returned no JSON body.
    }
    throw new Error(`${response.status} ${detail}`.trim());
  }
  return (await response.json()) as T;
}

export function getPursuitMembers(): Promise<PursuitMember[]> {
  return readJson<PursuitMember[]>("/api/pursuit/members");
}

export function getMyWork(): Promise<MyWork> {
  return readJson<MyWork>("/api/pursuit/my-work");
}

export function getTeamWork(): Promise<TeamWork> {
  return readJson<TeamWork>("/api/pursuit/team-work");
}

export function getPortfolio(): Promise<Portfolio> {
  return readJson<Portfolio>("/api/pursuit/portfolio");
}

export function getPursuitWorkspace(opportunityId: string): Promise<PursuitWorkspace> {
  return readJson<PursuitWorkspace>(
    `/api/pursuit/workspaces/${encodeURIComponent(opportunityId)}`,
  );
}

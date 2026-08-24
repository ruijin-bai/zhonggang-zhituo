import "server-only";

import { serverApiFetch } from "./server-api";

export type DailyBrief = {
  generated_at: string;
  window_hours: number;
  summary: {
    pending_candidates: number;
    new_candidates: number;
    recent_events: number;
    open_alerts: number;
    overdue_actions: number;
    due_soon_actions: number;
    review_due: number;
  };
  recent_events: Array<{
    kind: "opportunity_event";
    event_type: string;
    opportunity_id: string;
    title: string;
    occurred_at: string;
    payload: Record<string, unknown>;
  }>;
  attention: Array<{
    kind: "overdue_action" | "open_alert" | "review_due" | "candidate_review";
    severity: string;
    resource_id: string;
    opportunity_id: string | null;
    title: string;
    subtitle: string;
    owner?: string;
    due_at?: string | null;
    created_at?: string;
    message?: string;
  }>;
  note: string;
};

export type EntityIndexItem = {
  id: string;
  entity_type: string;
  canonical_name: string;
  country: string | null;
  status: string;
  opportunity_count: number;
  created_at: string;
  updated_at: string;
};

export type EntityDetail = {
  id: string;
  entity_type: string;
  canonical_name: string;
  country: string | null;
  status: string;
  aliases: Array<{
    alias: string;
    confidence: number;
    source_document_id: string | null;
  }>;
  opportunities: Array<{
    opportunity_id: string;
    role: string;
    confidence: number;
    source_count: number;
    last_seen_at: string;
    title: string;
    country: string | null;
    sector: string | null;
    stage: string | null;
  }>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

async function readJson<T>(path: string): Promise<T> {
  const response = await serverApiFetch(path, { cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // Preserve HTTP status if the backend does not return JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function getDailyBrief(windowHours = 24, limit = 8): Promise<DailyBrief> {
  return readJson<DailyBrief>(`/api/briefing/daily?window_hours=${windowHours}&limit=${limit}`);
}

export async function getEntities(query = "", limit = 200): Promise<EntityIndexItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query.trim()) params.set("q", query.trim());
  return readJson<EntityIndexItem[]>(`/api/entities?${params.toString()}`);
}

export async function getEntity(entityId: string): Promise<EntityDetail> {
  return readJson<EntityDetail>(`/api/entities/${encodeURIComponent(entityId)}`);
}

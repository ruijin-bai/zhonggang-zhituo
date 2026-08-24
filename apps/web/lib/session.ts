import "server-only";

import { serverApiFetch } from "./server-api";

export type SessionMeta = {
  version: string;
  data_backend: string;
  job_mode: string;
  ai_enabled: boolean;
  auth_mode: string;
  rls_enabled: boolean;
  organization: string;
  role: "viewer" | "analyst" | "manager" | "admin";
};

export async function getSessionMeta(): Promise<SessionMeta> {
  const response = await serverApiFetch("/api/meta", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Session meta unavailable: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as SessionMeta;
}

export function canReviewCandidates(role: SessionMeta["role"]): boolean {
  return role === "manager" || role === "admin";
}

export function canEditPursuit(role: SessionMeta["role"]): boolean {
  return role === "analyst" || role === "manager" || role === "admin";
}

export function canManagePursuit(role: SessionMeta["role"]): boolean {
  return role === "manager" || role === "admin";
}

import "server-only";

import { serverApiFetch } from "./server-api";

export type SearchResourceType = "opportunity" | "candidate" | "entity" | "evidence" | "source";

export type SearchResultItem = {
  resource_type: SearchResourceType;
  resource_id: string;
  title: string;
  subtitle: string;
  snippet: string;
  relevance_score: number;
  matched_fields: string[];
  opportunity_id: string | null;
  metadata: Record<string, unknown>;
};

export type SearchResponse = {
  query: string;
  filters: {
    resource_types: SearchResourceType[];
    country: string | null;
    sector: string | null;
    entity_role: string | null;
    source_rank: string | null;
  };
  count: number;
  results: SearchResultItem[];
  note: string;
};

export type CandidateItem = {
  id: string;
  status: string;
  discovery: {
    project_detected: boolean;
    title: string;
    country: string;
    region: string;
    sector: string;
    stage: string;
    owner: string;
    estimated_value_usd_m: number | null;
    summary: string;
    confidence: number;
    facts: Array<{
      field_name: string;
      value: string;
      score_hint: number | null;
      evidence_quote: string;
      confidence: number;
    }>;
    parties: Array<{
      role: string;
      name: string;
      country: string | null;
      evidence_quote: string;
      confidence: number;
    }>;
  };
  source_url: string | null;
  source_title: string;
  publisher: string;
  published_at: string;
  source_rank: string;
  duplicate_matches: Array<{
    opportunity_id: string;
    title: string;
    country: string;
    similarity: number;
  }>;
  source_document_id: string | null;
  processing_id: string | null;
  source_count: number;
  source_document_ids: string[];
  entities: Array<{
    entity_id: string;
    name: string;
    country: string | null;
    roles: string[];
    source_count: number;
  }>;
  created_at: string;
  updated_at: string;
};

export type OpportunityKnowledge = {
  opportunity: {
    id: string;
    title: string;
    country: string;
    region: string;
    sector: string;
    stage: string;
    owner: string;
    estimated_value_usd_m: number | null;
    summary: string;
    score: number;
    grade: string;
    confidence: number;
    decision: string;
    pursuit_thesis: string;
    next_actions: string[];
  };
  entities: Array<{
    entity_id: string;
    name: string;
    country: string | null;
    role: string;
    confidence: number;
    source_count: number;
    aliases: string[];
  }>;
  sources: Array<{
    source_id: string;
    source_document_id: string | null;
    title: string;
    publisher: string;
    published_at: string;
    source_rank: string;
    url: string | null;
  }>;
  evidence: Array<{
    evidence_id: string;
    source_id: string | null;
    rank: string;
    field_name: string | null;
    fact: string;
    confidence: number;
    publisher: string;
    source_url: string | null;
  }>;
  events: Array<{
    event_type: string;
    occurred_at: string;
    payload: Record<string, unknown>;
  }>;
  related_opportunities: Array<{
    opportunity_id: string;
    title: string;
    country: string;
    sector: string;
    stage: string;
    shared_entities: Array<{
      entity_id: string;
      name: string;
      role_in_related: string;
    }>;
  }>;
  provenance: {
    formal_source_count: number;
    immutable_source_document_count: number;
    evidence_count: number;
    entity_count: number;
  };
};

async function readJson<T>(path: string): Promise<T> {
  const response = await serverApiFetch(path, { cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // Preserve the HTTP status when the backend does not return JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function getKnowledgeSearch(input: {
  query: string;
  types?: string;
  country?: string;
  sector?: string;
  entityRole?: string;
  sourceRank?: string;
  limit?: number;
}): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: input.query, limit: String(input.limit ?? 30) });
  if (input.types) params.set("types", input.types);
  if (input.country) params.set("country", input.country);
  if (input.sector) params.set("sector", input.sector);
  if (input.entityRole) params.set("entity_role", input.entityRole);
  if (input.sourceRank) params.set("source_rank", input.sourceRank);
  return readJson<SearchResponse>(`/api/search?${params.toString()}`);
}

export async function getPendingCandidates(limit = 20): Promise<CandidateItem[]> {
  return readJson<CandidateItem[]>(`/api/candidates?status=pending&limit=${limit}`);
}

export async function getCandidate(candidateId: string): Promise<CandidateItem> {
  return readJson<CandidateItem>(`/api/candidates/${encodeURIComponent(candidateId)}`);
}

export async function getOpportunityKnowledge(opportunityId: string): Promise<OpportunityKnowledge> {
  return readJson<OpportunityKnowledge>(
    `/api/knowledge/opportunities/${encodeURIComponent(opportunityId)}`,
  );
}

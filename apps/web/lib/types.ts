export type ScoreBreakdown = {
  strategic_fit: number;
  project_maturity: number;
  financing: number;
  client_quality: number;
  capability_fit: number;
  local_position: number;
  competition: number;
  risk_control: number;
};

export type Evidence = {
  id: string;
  rank: "S" | "A" | "B" | "C" | "D";
  title: string;
  publisher: string;
  published_at: string;
  fact: string;
};

export type ScoreSnapshot = {
  date: string;
  total: number;
  grade: "A" | "B" | "C" | "D";
  note: string;
};

export type Opportunity = {
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
  grade: "A" | "B" | "C" | "D";
  confidence: number;
  decision: "GO" | "WATCH" | "CAUTION" | "NO-GO" | "INSUFFICIENT_EVIDENCE";
  breakdown: ScoreBreakdown;
  evidence: Evidence[];
  score_history: ScoreSnapshot[];
  pursuit_thesis: string;
  next_actions: string[];
  is_demo: boolean;
};

export type CountryRadar = {
  country: string;
  region: string;
  opportunity_count: number;
  pending_draft_count: number;
  source_count: number;
  evidence_count: number;
  high_grade_count: number;
  average_score: number | null;
  average_confidence: number | null;
  total_value_usd_m: number | null;
  activity_index: number;
  attractiveness_index: number | null;
  top_sectors: string[];
};

export type SectorRadar = {
  sector: string;
  opportunity_count: number;
  high_grade_count: number;
  average_score: number | null;
  total_value_usd_m: number | null;
};

export type RadarOverview = {
  opportunity_count: number;
  pending_draft_count: number;
  source_count: number;
  evidence_count: number;
  recent_event_count: number;
  country_count: number;
  countries: CountryRadar[];
  sectors: SectorRadar[];
  note: string;
};

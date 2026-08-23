import { demoOpportunities } from "./demo";
import type { Opportunity, RadarOverview } from "./types";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const ALLOW_DEMO_FALLBACK = process.env.NEXT_PUBLIC_ALLOW_DEMO_FALLBACK !== "false";

function apiFailure(message: string, error: unknown): never {
  console.error(`[Zhituo API] ${message}`, error);
  throw new Error(`${message}。生产模式不会回退到 Demo 数据，请检查 API、数据库与运行环境。`);
}

export async function getOpportunities(): Promise<Opportunity[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/opportunities`, { next: { revalidate: 30 } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    if (ALLOW_DEMO_FALLBACK) return demoOpportunities;
    return apiFailure("机会池读取失败", error);
  }
}

export async function getOpportunity(id: string): Promise<Opportunity | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/opportunities/${id}`, { next: { revalidate: 30 } });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    if (ALLOW_DEMO_FALLBACK) return demoOpportunities.find((item) => item.id === id) ?? null;
    return apiFailure("机会详情读取失败", error);
  }
}

function demoRadar(): RadarOverview {
  const countries = new Map<string, Opportunity[]>();
  for (const item of demoOpportunities) countries.set(item.country, [...(countries.get(item.country) ?? []), item]);
  const rows = [...countries.entries()].map(([country, items]) => {
    const rated = items.filter((item) => item.confidence >= 45);
    const average = rated.length ? rated.reduce((sum, item) => sum + item.score, 0) / rated.length : null;
    const high = rated.filter((item) => item.grade === "A").length;
    const avgConfidence = items.reduce((sum, item) => sum + item.confidence, 0) / items.length;
    return {
      country,
      region: items[0].region,
      opportunity_count: items.length,
      pending_draft_count: 0,
      source_count: items.reduce((sum, item) => sum + item.evidence.length, 0),
      evidence_count: items.reduce((sum, item) => sum + item.evidence.length, 0),
      high_grade_count: high,
      average_score: average === null ? null : Math.round(average * 10) / 10,
      average_confidence: Math.round(avgConfidence * 10) / 10,
      total_value_usd_m: items.some((item) => item.estimated_value_usd_m !== null) ? items.reduce((sum, item) => sum + (item.estimated_value_usd_m ?? 0), 0) : null,
      activity_index: Math.min(100, items.length * 18 + items.reduce((sum, item) => sum + item.evidence.length, 0) * 7),
      attractiveness_index: average === null ? null : Math.min(100, Math.round(average * 0.72 + (high / rated.length) * 18 + (avgConfidence / 100) * 10)),
      top_sectors: [...new Set(items.map((item) => item.sector))].slice(0, 3),
    };
  }).sort((a, b) => (b.attractiveness_index ?? -1) - (a.attractiveness_index ?? -1));
  return {
    opportunity_count: demoOpportunities.length,
    pending_draft_count: 0,
    source_count: demoOpportunities.reduce((sum, item) => sum + item.evidence.length, 0),
    evidence_count: demoOpportunities.reduce((sum, item) => sum + item.evidence.length, 0),
    recent_event_count: 0,
    country_count: rows.length,
    countries: rows,
    sectors: [],
    note: "当前为内置 Demo 雷达。启动 API 与数据库后将显示真实草稿、来源和证据活跃度。",
  };
}

export async function getRadar(): Promise<RadarOverview> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/radar`, { next: { revalidate: 20 } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    if (ALLOW_DEMO_FALLBACK) return demoRadar();
    return apiFailure("市场雷达读取失败", error);
  }
}

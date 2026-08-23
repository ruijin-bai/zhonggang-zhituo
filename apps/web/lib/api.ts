import { demoOpportunities } from "./demo";
import type { Opportunity } from "./types";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export async function getOpportunities(): Promise<Opportunity[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/opportunities`, { next: { revalidate: 30 } });
    if (!response.ok) throw new Error("API unavailable");
    return await response.json();
  } catch {
    return demoOpportunities;
  }
}

export async function getOpportunity(id: string): Promise<Opportunity | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/opportunities/${id}`, { next: { revalidate: 30 } });
    if (!response.ok) throw new Error("API unavailable");
    return await response.json();
  } catch {
    return demoOpportunities.find((item) => item.id === id) ?? null;
  }
}

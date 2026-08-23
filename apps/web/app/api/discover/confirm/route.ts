import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { draft_id, ...edits } = body;
    if (!draft_id) return NextResponse.json({ detail: "缺少 draft_id" }, { status: 400 });
    const response = await fetch(`${API_BASE_URL}/api/discovery/drafts/${encodeURIComponent(draft_id)}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(edits),
      cache: "no-store",
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "智拓 API 当前不可用，请先启动 apps/api 服务。" }, { status: 503 });
  }
}

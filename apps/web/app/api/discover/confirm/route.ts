import { NextRequest, NextResponse } from "next/server";
import { serverApiFetch } from "@/lib/server-api";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { draft_id, ...edits } = body;
    if (!draft_id) return NextResponse.json({ detail: "缺少 draft_id" }, { status: 400 });

    const response = await serverApiFetch(
      `/api/discovery/drafts/${encodeURIComponent(draft_id)}/confirm`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(edits),
        cache: "no-store",
      },
    );
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    console.error("[Zhituo BFF] discovery confirmation failed", error);
    return NextResponse.json({ detail: "智拓 API 当前不可用或认证失败。" }, { status: 503 });
  }
}

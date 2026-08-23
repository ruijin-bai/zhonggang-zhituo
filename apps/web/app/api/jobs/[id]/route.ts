import { NextRequest, NextResponse } from "next/server";
import { serverApiFetch } from "@/lib/server-api";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const response = await serverApiFetch(`/api/jobs/${encodeURIComponent(id)}`, {
      cache: "no-store",
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    console.error("[Zhituo BFF] job status failed", error);
    return NextResponse.json({ detail: "后台任务状态读取失败" }, { status: 503 });
  }
}

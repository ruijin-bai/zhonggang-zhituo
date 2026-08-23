import { NextRequest, NextResponse } from "next/server";
import { serverApiFetch } from "@/lib/server-api";

const BODY_JOB_PATHS: Record<string, string> = {
  "discovery.scan": "/api/jobs/discovery/scan",
  "discovery.batch": "/api/jobs/discovery/batch",
  "source.ingest": "/api/jobs/sources/ingest",
};

const OPPORTUNITY_JOB_SUFFIXES: Record<string, string> = {
  "opportunity.analyze": "analyze",
  "strategy.generate": "strategy/generate",
  "strategy.red_team": "strategy/red-team",
};

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const kind = typeof body.kind === "string" ? body.kind : "";
    const opportunityId = typeof body.opportunity_id === "string" ? body.opportunity_id : "";

    let path = BODY_JOB_PATHS[kind];
    let backendBody: string | undefined;
    if (path) {
      backendBody = JSON.stringify(body.payload ?? {});
    } else if (OPPORTUNITY_JOB_SUFFIXES[kind]) {
      if (!opportunityId) {
        return NextResponse.json({ detail: "该任务缺少 opportunity_id" }, { status: 400 });
      }
      path = `/api/jobs/opportunities/${encodeURIComponent(opportunityId)}/${OPPORTUNITY_JOB_SUFFIXES[kind]}`;
    } else {
      return NextResponse.json({ detail: "不支持的后台任务类型" }, { status: 400 });
    }

    const response = await serverApiFetch(path, {
      method: "POST",
      headers: backendBody ? { "Content-Type": "application/json" } : undefined,
      body: backendBody,
      cache: "no-store",
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    console.error("[Zhituo BFF] job submission failed", error);
    return NextResponse.json({ detail: "后台任务提交失败" }, { status: 503 });
  }
}

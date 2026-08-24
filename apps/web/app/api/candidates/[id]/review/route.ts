import { createHash } from "node:crypto";

import { NextRequest, NextResponse } from "next/server";

import { serverApiFetch } from "@/lib/server-api";

type ReviewAction = "confirm" | "reject" | "attach";

type ReviewBody = {
  action?: ReviewAction;
  opportunity_id?: string;
  edits?: Record<string, unknown>;
};

function idempotencyKey(candidateId: string, body: ReviewBody): string {
  const digest = createHash("sha256")
    .update(JSON.stringify(body))
    .digest("hex")
    .slice(0, 32);
  return `web-candidate-${candidateId.slice(0, 24)}-${body.action ?? "unknown"}-${digest}`;
}

async function backendError(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return { detail: `${response.status} ${response.statusText}` };
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  let body: ReviewBody;
  try {
    body = (await request.json()) as ReviewBody;
  } catch {
    return NextResponse.json({ detail: "请求体必须是 JSON" }, { status: 400 });
  }

  if (!body.action || !["confirm", "reject", "attach"].includes(body.action)) {
    return NextResponse.json({ detail: "不支持的 Candidate 审核动作" }, { status: 400 });
  }

  let path: string;
  let backendBody: string | undefined;
  if (body.action === "confirm") {
    path = `/api/discovery/drafts/${encodeURIComponent(id)}/confirm`;
    backendBody = JSON.stringify(body.edits ?? {});
  } else if (body.action === "reject") {
    path = `/api/candidates/${encodeURIComponent(id)}/reject`;
  } else {
    const opportunityId = body.opportunity_id?.trim();
    if (!opportunityId) {
      return NextResponse.json({ detail: "挂接补充证据时必须选择正式 Opportunity" }, { status: 400 });
    }
    path = `/api/candidates/${encodeURIComponent(id)}/attach/${encodeURIComponent(opportunityId)}`;
  }

  try {
    const response = await serverApiFetch(path, {
      method: "POST",
      headers: {
        "Idempotency-Key": idempotencyKey(id, body),
        ...(backendBody ? { "Content-Type": "application/json" } : {}),
      },
      body: backendBody,
      cache: "no-store",
    });
    const payload = await backendError(response);
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    console.error("[Zhituo BFF] candidate review failed", error);
    return NextResponse.json({ detail: "Candidate 审核服务暂不可用" }, { status: 503 });
  }
}

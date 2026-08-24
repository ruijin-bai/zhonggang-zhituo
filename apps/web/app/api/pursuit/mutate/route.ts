import { NextRequest, NextResponse } from "next/server";

import { serverApiFetch } from "@/lib/server-api";

type PursuitAction =
  | "open_workspace"
  | "upsert_participant"
  | "create_work_item"
  | "update_work_item"
  | "open_gate"
  | "request_review"
  | "submit_review"
  | "record_decision";

type MutationBody = {
  action?: PursuitAction;
  idempotency_key?: string;
  opportunity_id?: string;
  workspace_id?: string;
  work_item_id?: string;
  gate_id?: string;
  review_id?: string;
  payload?: Record<string, unknown>;
};

function required(value: string | undefined, label: string): string {
  const normalized = value?.trim();
  if (!normalized) throw new Error(`${label} 不能为空`);
  return normalized;
}

function mutationTarget(body: MutationBody): { path: string; method: "POST" | "PUT" } {
  switch (body.action) {
    case "open_workspace":
      return {
        path: `/api/pursuit/workspaces/${encodeURIComponent(required(body.opportunity_id, "opportunity_id"))}/open`,
        method: "POST",
      };
    case "upsert_participant":
      return {
        path: `/api/pursuit/workspaces/${encodeURIComponent(required(body.workspace_id, "workspace_id"))}/participants`,
        method: "POST",
      };
    case "create_work_item":
      return {
        path: `/api/pursuit/workspaces/${encodeURIComponent(required(body.workspace_id, "workspace_id"))}/work-items`,
        method: "POST",
      };
    case "update_work_item":
      return {
        path: `/api/pursuit/work-items/${encodeURIComponent(required(body.work_item_id, "work_item_id"))}`,
        method: "PUT",
      };
    case "open_gate":
      return {
        path: `/api/pursuit/workspaces/${encodeURIComponent(required(body.workspace_id, "workspace_id"))}/gates`,
        method: "POST",
      };
    case "request_review":
      return {
        path: `/api/pursuit/gates/${encodeURIComponent(required(body.gate_id, "gate_id"))}/reviews`,
        method: "POST",
      };
    case "submit_review":
      return {
        path: `/api/pursuit/reviews/${encodeURIComponent(required(body.review_id, "review_id"))}`,
        method: "PUT",
      };
    case "record_decision":
      return {
        path: `/api/pursuit/gates/${encodeURIComponent(required(body.gate_id, "gate_id"))}/decisions`,
        method: "POST",
      };
    default:
      throw new Error("不支持的 Pursuit 操作");
  }
}

async function responsePayload(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return { detail: `${response.status} ${response.statusText}` };
  }
}

export async function POST(request: NextRequest) {
  let body: MutationBody;
  try {
    body = (await request.json()) as MutationBody;
  } catch {
    return NextResponse.json({ detail: "请求体必须是 JSON" }, { status: 400 });
  }

  const key = body.idempotency_key?.trim();
  if (!key || key.length < 8 || key.length > 180 || /\s/.test(key)) {
    return NextResponse.json({ detail: "缺少有效的 idempotency_key" }, { status: 400 });
  }

  let target: { path: string; method: "POST" | "PUT" };
  try {
    target = mutationTarget(body);
  } catch (error) {
    return NextResponse.json(
      { detail: error instanceof Error ? error.message : "Pursuit 操作参数错误" },
      { status: 400 },
    );
  }

  try {
    const response = await serverApiFetch(target.path, {
      method: target.method,
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": key,
      },
      body: JSON.stringify(body.payload ?? {}),
      cache: "no-store",
    });
    return NextResponse.json(await responsePayload(response), { status: response.status });
  } catch (error) {
    console.error("[Zhituo BFF] pursuit mutation failed", error);
    return NextResponse.json({ detail: "Pursuit 协同服务暂不可用" }, { status: 503 });
  }
}

import { NextResponse } from "next/server";

export async function POST() {
  return NextResponse.json(
    { detail: "同步商机扫描入口已停用，请使用 /api/jobs/submit 提交 discovery.scan 后台任务。" },
    { status: 410 },
  );
}

type JobSubmission = {
  job_id: string;
  job_type: string;
  state: string;
  status_url: string;
};

type JobSnapshot<T> = {
  job_id: string;
  state: string;
  ready: boolean;
  successful: boolean | null;
  result: T | null;
  error: string | null;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function runQueuedJob<T>(
  kind: string,
  payload: unknown,
  options: { opportunityId?: string; timeoutMs?: number; idempotencyKey?: string } = {},
): Promise<T> {
  const idempotencyKey = options.idempotencyKey ?? crypto.randomUUID();
  const submit = await fetch("/api/jobs/submit", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({
      kind,
      opportunity_id: options.opportunityId ?? null,
      payload,
    }),
  });
  const submitted = (await submit.json()) as JobSubmission & { detail?: string };
  if (!submit.ok) throw new Error(submitted.detail ?? `任务提交失败：HTTP ${submit.status}`);

  const deadline = Date.now() + (options.timeoutMs ?? 120_000);
  while (Date.now() < deadline) {
    await sleep(800);
    const response = await fetch(`/api/jobs/${encodeURIComponent(submitted.job_id)}`, {
      cache: "no-store",
    });
    const snapshot = (await response.json()) as JobSnapshot<T> & { detail?: string };
    if (!response.ok) throw new Error(snapshot.detail ?? `任务状态读取失败：HTTP ${response.status}`);
    if (!snapshot.ready) continue;
    if (snapshot.successful && snapshot.result !== null) return snapshot.result;
    throw new Error(snapshot.error ?? "后台任务执行失败");
  }
  throw new Error("后台任务等待超时，可稍后根据任务状态继续查询。");
}

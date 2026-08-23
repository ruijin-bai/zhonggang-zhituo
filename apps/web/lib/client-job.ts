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

async function submitWithRetry(
  requestBody: string,
  idempotencyKey: string,
): Promise<JobSubmission> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const response = await fetch("/api/jobs/submit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: requestBody,
      });
      const payload = (await response.json()) as JobSubmission & { detail?: string };
      if (!response.ok) throw new Error(payload.detail ?? `任务提交失败：HTTP ${response.status}`);
      return payload;
    } catch (error) {
      lastError = error;
      if (attempt === 0) await sleep(500);
    }
  }
  throw lastError instanceof Error ? lastError : new Error("后台任务提交失败");
}

export async function runQueuedJob<T>(
  kind: string,
  payload: unknown,
  options: { opportunityId?: string; timeoutMs?: number; idempotencyKey?: string } = {},
): Promise<T> {
  const idempotencyKey = options.idempotencyKey ?? crypto.randomUUID();
  const requestBody = JSON.stringify({
    kind,
    opportunity_id: options.opportunityId ?? null,
    payload,
  });
  const submitted = await submitWithRetry(requestBody, idempotencyKey);

  const deadline = Date.now() + (options.timeoutMs ?? 120_000);
  let transientFailures = 0;
  while (Date.now() < deadline) {
    await sleep(800);
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(submitted.job_id)}`, {
        cache: "no-store",
      });
      const snapshot = (await response.json()) as JobSnapshot<T> & { detail?: string };
      if (!response.ok) {
        if (response.status >= 500 && transientFailures < 3) {
          transientFailures += 1;
          continue;
        }
        throw new Error(snapshot.detail ?? `任务状态读取失败：HTTP ${response.status}`);
      }
      transientFailures = 0;
      if (!snapshot.ready) continue;
      if (snapshot.successful && snapshot.result !== null) return snapshot.result;
      throw new Error(snapshot.error ?? "后台任务执行失败");
    } catch (error) {
      if (transientFailures < 3) {
        transientFailures += 1;
        continue;
      }
      throw error;
    }
  }
  throw new Error("后台任务等待超时，可稍后根据任务状态继续查询。");
}

import "server-only";
import { headers } from "next/headers";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
const API_AUTH_MODE = process.env.API_AUTH_MODE ?? "development_header";

function copyIfPresent(source: Headers, target: Headers, name: string) {
  const value = source.get(name);
  if (value) target.set(name, value);
}

export async function serverApiFetch(path: string, init: RequestInit = {}) {
  const incoming = await headers();
  const outgoing = new Headers(init.headers);

  copyIfPresent(incoming, outgoing, "x-request-id");
  copyIfPresent(incoming, outgoing, "x-correlation-id");
  copyIfPresent(incoming, outgoing, "x-zhituo-organization");
  copyIfPresent(incoming, outgoing, "idempotency-key");

  if (API_AUTH_MODE === "trusted_proxy") {
    const user = incoming.get("x-zhituo-user");
    const secret = process.env.API_TRUSTED_PROXY_SECRET;
    if (!user || !secret) {
      throw new Error("Web BFF trusted_proxy identity is not configured");
    }
    outgoing.set("X-Zhituo-User", user);
    outgoing.set("X-Zhituo-Gateway-Secret", secret);
  } else if (API_AUTH_MODE === "oidc") {
    const authorization = incoming.get("authorization");
    if (!authorization) {
      throw new Error("Web BFF did not receive an OIDC bearer token");
    }
    outgoing.set("Authorization", authorization);
  } else {
    // Development only. API production guardrails reject this mode.
    copyIfPresent(incoming, outgoing, "x-zhituo-user");
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: outgoing,
  });
}

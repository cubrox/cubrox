#!/usr/bin/env node
// provider: render-only
// scripts/render-deploy-status.mjs
//
// Queries Render's API for the deploy status of a specific commit SHA on
// the configured service. Consumed by the `/drain` skill (#180; step 9
// of the per-iteration cycle) so the drain can wait for a *specific*
// deploy to land before proceeding to validation, instead of the v1
// fallback of probing the public URL with curl (which only tells you
// "some version of the site is alive," not "this merge's deploy is alive").
//
// Output: a single JSON line on stdout —
//   { live: <boolean>, status: <string|null>, source: "render"|"unavailable",
//     reason?: "...", hint?: "...", deployId?: "...", sha?: "..." }
//
// Exit codes: 0 always. If Render is unreachable, unconfigured, or the
// deploy hasn't appeared yet, we emit source="unavailable" or
// status="pending" and let the caller decide whether to fall back to
// the curl-based liveness check (per docs/testing/render-gating.md).
//
// The optional `hint` field disambiguates "unavailable" cases for the
// operator (per #217): env-vars-missing-from-process points at the
// fish-universal-vars-not-inherited-by-Bash trap (saved lesson
// claude-code-bash-does-not-inherit-fish-universal-vars); API-call-failed
// points at the Render side. The `reason` field still names the raw
// failure for log/debug purposes; the `hint` names the likely fix.
//
// API contract (Render — list deploys for a service):
//   GET ${RENDER_API_BASE}/services/${RENDER_SERVICE_ID}/deploys?limit=20
//   Bearer ${RENDER_API_TOKEN}
// Response: array of items, each wrapping a deploy with id, status, and
// commit.id (= SHA). We search the recent slice for a matching SHA.

import { readFileSync } from "node:fs";

export const DEFAULT_API_BASE = "https://api.render.com/v1";
const DEPLOYS_LIMIT = 20;

const LIVE_STATUS = "live";

function readConfig(env) {
  const apiBase = env.RENDER_API_BASE ?? DEFAULT_API_BASE;
  const token = env.RENDER_API_TOKEN;
  const serviceId = env.RENDER_SERVICE_ID;
  const missing = [];
  if (!token) missing.push("RENDER_API_TOKEN");
  if (!serviceId) missing.push("RENDER_SERVICE_ID");
  if (missing.length > 0) return { configured: false, missing };
  return { configured: true, apiBase, token, serviceId };
}

/**
 * Defensively extract the deploy object from a list-deploys response item.
 * Render's list-deploys response wraps each deploy in a `{cursor, deploy}`
 * envelope; some clients see the deploy at the top level. We handle both.
 *
 * @param {any} item - one element of the deploys response array
 * @returns {object|null}
 */
function extractDeploy(item) {
  if (!item || typeof item !== "object") return null;
  if (item.deploy && typeof item.deploy === "object") return item.deploy;
  if (typeof item.id === "string" && typeof item.status === "string") return item;
  return null;
}

/**
 * Query Render for the deploy whose commit SHA matches `sha`. Returns a
 * structured envelope describing the deploy's status (or unavailability).
 *
 * Never throws. Caller decides whether to retry, poll, or fall back.
 *
 * @param {{
 *   sha: string,
 *   env?: Record<string, string | undefined>,
 *   fetchImpl?: typeof fetch,
 * }} options
 */
export async function getDeployStatus({
  sha,
  env = process.env,
  fetchImpl = globalThis.fetch,
}) {
  if (!sha || typeof sha !== "string") {
    return {
      live: false,
      status: null,
      source: "unavailable",
      reason: "missing sha argument",
    };
  }

  const config = readConfig(env);
  if (!config.configured) {
    return {
      live: false,
      status: null,
      source: "unavailable",
      reason: `missing env: ${config.missing.join(", ")}`,
      hint: 'env vars not visible to this process; if set in fish, retry via \'fish -c "node scripts/render-deploy-status.mjs <SHA>"\'',
    };
  }

  const url = `${config.apiBase.replace(/\/$/, "")}/services/${config.serviceId}/deploys?limit=${DEPLOYS_LIMIT}`;

  let response;
  try {
    response = await fetchImpl(url, {
      headers: {
        Authorization: `Bearer ${config.token}`,
        Accept: "application/json",
      },
    });
  } catch (err) {
    const reason = `fetch failed: ${err instanceof Error ? err.message : String(err)}`;
    return {
      live: false,
      status: null,
      source: "unavailable",
      reason,
      hint: `Render API call failed: ${reason}`,
    };
  }

  if (!response.ok) {
    const reason = `HTTP ${response.status}`;
    return {
      live: false,
      status: null,
      source: "unavailable",
      reason,
      hint: `Render API call failed: ${reason}`,
    };
  }

  let body;
  try {
    body = await response.json();
  } catch (err) {
    const reason = `JSON parse failed: ${err instanceof Error ? err.message : String(err)}`;
    return {
      live: false,
      status: null,
      source: "unavailable",
      reason,
      hint: `Render API call failed: ${reason}`,
    };
  }

  if (!Array.isArray(body)) {
    const reason = "unexpected response shape: expected array";
    return {
      live: false,
      status: null,
      source: "unavailable",
      reason,
      hint: `Render API call failed: ${reason}`,
    };
  }

  for (const item of body) {
    const deploy = extractDeploy(item);
    if (!deploy) continue;
    const commitSha = deploy.commit?.id;
    if (typeof commitSha !== "string") continue;
    if (commitSha === sha || commitSha.startsWith(sha) || sha.startsWith(commitSha)) {
      const status = typeof deploy.status === "string" ? deploy.status : null;
      return {
        live: status === LIVE_STATUS,
        status,
        source: "render",
        deployId: typeof deploy.id === "string" ? deploy.id : undefined,
        sha: commitSha,
      };
    }
  }

  return {
    live: false,
    status: "pending",
    source: "render",
    sha,
    reason: "no deploy found for this sha in the recent window",
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const sha = process.argv[2];
  if (!sha) {
    console.error("Usage: node scripts/render-deploy-status.mjs <commit-sha>");
    console.error("Required env: RENDER_API_TOKEN, RENDER_SERVICE_ID");
    console.error("Optional env: RENDER_API_BASE (default: https://api.render.com/v1)");
    process.exit(2);
  }
  const result = await getDeployStatus({ sha });
  if (result.source === "unavailable") {
    console.error(`render-deploy-status: ${result.reason}`);
    if (result.hint) console.error(`render-deploy-status hint: ${result.hint}`);
  }
  console.log(JSON.stringify(result));
}

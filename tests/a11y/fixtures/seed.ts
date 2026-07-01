import type { APIRequestContext, BrowserContext } from "@playwright/test";

export type Variant = "default" | "high-contrast" | "large-text" | "bionic";

export interface SeedResult {
  passageId: string;
  variant: Variant;
}

/**
 * Provision a fresh user + passage (+ optional Preference) via the
 * test-only seed route, then propagate the session cookie onto the
 * BrowserContext so navigations are authenticated.
 *
 * The /test/seed-passage-and-login route is gated behind
 * MASTERKEY_TEST_SEED_ENABLED=true at app boot — see
 * `app/api/test_seed.py`. Production Cloud Run revisions don't set
 * the var; the seed route returns 404 there because the router is
 * never registered.
 *
 * Implementation note: Playwright's `request` fixture maintains a
 * separate cookie jar from the browser context. The seed response's
 * `Set-Cookie` lands in `request.storageState().cookies`; we copy
 * those into `context.addCookies(...)` so `page.goto()` carries the
 * authenticated session.
 */
export async function seedAndLogin(
  request: APIRequestContext,
  context: BrowserContext,
  variant: Variant,
  opts: { withQuestions?: boolean } = {},
): Promise<SeedResult> {
  // `with_questions` (A11Y-5 #126) also seeds the comprehension cache so
  // the questions panel renders its real answer UI from a cache hit.
  const q = opts.withQuestions ? "&with_questions=true" : "";
  const response = await request.post(
    `/test/seed-passage-and-login?variant=${variant}${q}`,
  );
  if (!response.ok()) {
    throw new Error(
      `seed failed: ${response.status()} ${await response.text()}`,
    );
  }

  const body = (await response.json()) as {
    passage_id: string;
    variant: Variant;
  };

  const state = await request.storageState();
  await context.addCookies(state.cookies);

  return { passageId: body.passage_id, variant: body.variant };
}

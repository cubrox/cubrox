import { test, expect } from "@playwright/test";

/**
 * Smoke test for the a11y harness.
 *
 * Hits /api/health to prove the webServer started, browser navigated,
 * and the test runner reports pass/fail correctly. Real accessibility
 * assertions land in A11Y-2 (#25), which adds axe-core checks against
 * the reading surface and sidebar across the preference matrix.
 *
 * /api/health is intentionally minimal — no DB, no auth — so this test
 * doesn't depend on Postgres being up. A11Y-2 will figure out the
 * per-test DB strategy for the real reading-view assertions.
 */
test("smoke: /api/health responds 200 and renders", async ({ page }) => {
  const response = await page.goto("/api/health");
  expect(response?.status()).toBe(200);

  // The health-check route returns JSON. Confirm the expected status
  // field is visible in the rendered body so we know we reached the
  // FastAPI app and not some intermediary error page.
  const body = await page.locator("body").textContent();
  expect(body).toContain("ok");
});

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Login + verify flow accessibility assertions (A11Y-4 #121).
 *
 * Epic #8 covered the reading surface; epic #3's acceptance also asked
 * for an a11y audit of the login + verify flow, which had no automated
 * coverage. Every page here is PUBLIC, so — unlike reading_surface.spec
 * — these tests need no seed/login fixture.
 *
 * Surfaces:
 *   - GET /              → landing page + magic-link sign-in form
 *   - GET /auth/callback → Stage 1 hash-extractor bridge page. With no
 *     token/hash its inline JS renders the terminal "link invalid or
 *     expired" state, which is what a user sees on a bad link — so it's
 *     the right state to audit.
 *
 * Gate (matches reading_surface.spec): ZERO `serious`/`critical`
 * violations under WCAG 2.0 A+AA. Moderate/minor are logged, not failed.
 */

async function expectNoA11yBlockers(page: Page, label: string): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();

  const blockers = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );

  if (blockers.length > 0) {
    console.log(`[a11y blockers — ${label}]`, JSON.stringify(blockers, null, 2));
  }

  const nonBlocking = results.violations.filter(
    (v) => v.impact !== "critical" && v.impact !== "serious",
  );
  if (nonBlocking.length > 0) {
    console.log(
      `[a11y non-blocking — ${label}]`,
      nonBlocking.map((v) => `${v.id} (${v.impact})`).join(", "),
    );
  }

  expect(blockers, `axe found serious/critical violations on ${label}`).toHaveLength(0);
}

test("login page a11y: sign-in form", async ({ page }) => {
  await page.goto("/");
  // Anchor on the sign-in form so the scan runs against rendered markup.
  await expect(page.locator("#signin-form")).toBeVisible();

  await expectNoA11yBlockers(page, "GET /");
});

test("verify flow a11y: callback bridge (invalid-link state)", async ({ page }) => {
  // No token + no hash → the bridge JS renders its terminal error state.
  await page.goto("/auth/callback");
  // Wait for the JS to swap in the "Try again" link before scanning.
  await expect(page.getByRole("link", { name: /try again/i })).toBeVisible();

  await expectNoA11yBlockers(page, "GET /auth/callback (invalid link)");
});

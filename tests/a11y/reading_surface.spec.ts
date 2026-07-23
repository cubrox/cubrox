import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { seedAndLogin, type Variant } from "./fixtures/seed";

/**
 * Reading-surface accessibility assertions (A11Y-2 #25).
 *
 * Each test exercises one representative preference combination by
 * provisioning an isolated user + passage + Preference row via the
 * test-only seed route, navigating the authenticated browser to
 * /read/<passage_id>, and running axe-core against the rendered page.
 *
 * Gate: ZERO `serious` or `critical` violations under WCAG 2.0 A+AA
 * rules. `moderate` and `minor` findings are surfaced in the test
 * output for future follow-up but don't fail the build — those tend
 * to be opinionated rule judgments rather than user-blocking issues.
 *
 * Each variant tests one axis at a time so a regression points
 * clearly at which preference broke a11y:
 *   - default      → no Preference row; full DEFAULT_PREFERENCES path
 *   - high-contrast → dark bg + light fg (dark-mode users)
 *   - large-text   → 28px font (low-vision users)
 *   - bionic       → bionic_enabled=true (the bionicize transform)
 *   - focus-mode   → focus_mode_enabled=true (dimmed non-active sections)
 */

const VARIANTS: Variant[] = [
  "default",
  "high-contrast",
  "large-text",
  "bionic",
  "focus-mode",
];

for (const variant of VARIANTS) {
  test(`reading surface a11y: ${variant}`, async ({ page, context, request }) => {
    const { passageId } = await seedAndLogin(request, context, variant);

    await page.goto(`/read/${passageId}`);
    // Wait for the reading-surface element to render — the seed
    // passage has known content, so we anchor on that.
    await expect(page.locator("#reading-surface")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const blockers = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );

    if (blockers.length > 0) {
      // Print the violations so failure output is actionable. Each
      // violation includes the rule id, impact, and the HTML of the
      // offending node — enough to reproduce locally.
      console.log(
        `[a11y blockers — ${variant}]`,
        JSON.stringify(blockers, null, 2),
      );
    }

    // Surface non-blocking findings for future tickets to address.
    const nonBlocking = results.violations.filter(
      (v) => v.impact !== "critical" && v.impact !== "serious",
    );
    if (nonBlocking.length > 0) {
      console.log(
        `[a11y non-blocking — ${variant}]`,
        nonBlocking.map((v) => `${v.id} (${v.impact})`).join(", "),
      );
    }

    expect(blockers, "axe found serious/critical violations").toHaveLength(0);
  });
}

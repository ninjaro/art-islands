import { expect, test } from "@playwright/test";
import { fetchCatalog, openApp } from "./helpers";

test("work card shows contributors by role, duration, content guide, and grouped concepts", async ({ page }) => {
  await openApp(page);
  const catalog = await fetchCatalog(page);
  const film = catalog.find((entry) => entry.hasDuration && entry.contributorRoles.includes("director"));
  expect(film).toBeDefined();

  await page.getByLabel("Search works, concepts, and contributors").fill(film!.label.slice(0, 24));
  await page.locator("td.label-cell", { hasText: film!.label.slice(0, 24) }).first().click();

  const card = page.locator(".entity-window").first();
  await expect(card).toBeVisible();

  // Contributors grouped by role.
  await expect(card.locator(".work-section h3", { hasText: "Contributors" })).toBeVisible();
  await expect(card.locator(".contributor-roles dt", { hasText: "Director" })).toBeVisible();

  // Duration formatted for humans.
  await expect(card.locator(".entity-meta")).toContainText(/\d+ h \d+ min|\d+ min/);

  // Concepts grouped by category with collapsible sections.
  await expect(card.locator(".work-section h3", { hasText: "Concepts" })).toBeVisible();
  expect(await card.locator(".concept-category summary").count()).toBeGreaterThan(0);

  // External references with human-readable names, no raw ids or JSON.
  await expect(card.locator(".ref-list a").first()).toBeVisible();
  const cardText = (await card.textContent()) ?? "";
  expect(cardText).not.toMatch(/\{"|entityId|conceptId/);
});

test("content guide section appears for works with advisories", async ({ page }) => {
  await openApp(page);
  // Advisories cover nearly the whole catalog; the first row qualifies.
  await page.locator("table tbody tr").first().click();
  const card = page.locator(".entity-window").first();
  await expect(card.locator(".work-section h3", { hasText: "Content guide" })).toBeVisible();
  // Advisory severity is shown as a text level, never color alone.
  await expect(card.locator(".advisory-level").first()).toHaveText(/high|moderate|mild/);
});

test("narrow screens present the card as a bottom sheet with an obvious close action", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await openApp(page);

  await page.locator("table tbody tr").first().evaluate((row) => (row as HTMLElement).click());
  const sheet = page.locator(".entity-window.sheet");
  await expect(sheet).toBeVisible();

  const box = (await sheet.boundingBox())!;
  expect(box.x).toBeLessThanOrEqual(1);
  expect(box.width).toBeGreaterThanOrEqual(388);

  // Close is reachable without dragging anything.
  await sheet.locator(".close-button").click();
  await expect(page.locator(".entity-window")).toHaveCount(0);
});

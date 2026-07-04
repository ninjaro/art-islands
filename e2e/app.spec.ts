import { expect, test } from "@playwright/test";
import { BASE, openApp } from "./helpers";

test("all four views load and data requests use the Pages base path", async ({ page }) => {
  const failed: string[] = [];
  const requested: string[] = [];
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/")) requested.push(url.pathname);
    if (response.status() >= 400) failed.push(`${response.status()} ${response.url()}`);
  });

  await openApp(page);
  await expect(page.locator("table tbody tr").first()).toBeVisible();

  await page.click('nav button:has-text("Recommendations")');
  await expect(page.locator(".empty")).toContainText("Like several works");

  await page.click('nav button:has-text("Evolution")');
  await expect(page.locator(".evo-node").first()).toBeVisible();
  await expect(page.locator(".graph-disclaimer")).toContainText(
    "Branches are inferred from date and tag similarity. They do not prove direct influence.",
  );

  await page.click('nav button:has-text("Islands")');
  await expect(page.locator(".empty")).toContainText("Rate some works");

  expect(failed).toEqual([]);
  const appRequests = requested.filter((path) => path.includes("."));
  expect(appRequests.length).toBeGreaterThan(0);
  for (const path of appRequests) {
    expect(path.startsWith(BASE)).toBeTruthy();
  }
});

test("ratings synchronize across views and survive reload", async ({ page }) => {
  await openApp(page);

  await page.locator("tbody tr").first().locator(".rating-buttons .like").click();
  await expect(page.locator(".rating-summary span")).toHaveText("1 rated");

  // Recommendations react to the like.
  await page.click('nav button:has-text("Recommendations")');
  await expect(page.locator(".recommendation-table tbody tr").first()).toBeVisible();

  // Rating inside Recommendations recomputes the list and syncs back to Browse.
  const recommendedLabel = await page
    .locator(".recommendation-table tbody tr .label-cell")
    .first()
    .textContent();
  await page.locator(".recommendation-table tbody tr").first().locator(".rating-buttons .like").click();
  await expect(
    page.locator(".recommendation-table .label-cell", { hasText: recommendedLabel! }),
  ).toHaveCount(0);
  await expect(page.locator(".rating-summary span")).toHaveText("2 rated");

  await page.click('nav button:has-text("Browse")');
  await expect(page.locator("tbody .icon-button.active.like")).toHaveCount(2);

  // Survives reload.
  await page.reload();
  await page.waitForSelector("table tbody tr");
  await expect(page.locator(".rating-summary span")).toHaveText("2 rated");
});

test("clearing ratings resets Recommendations and Islands", async ({ page }) => {
  await openApp(page);
  await page.locator("tbody tr").first().locator(".rating-buttons .like").click();

  page.once("dialog", (dialog) => dialog.accept());
  await page.click(".clear-ratings");
  await expect(page.locator(".rating-summary span")).toHaveText("0 rated");

  await page.click('nav button:has-text("Recommendations")');
  await expect(page.locator(".empty")).toContainText("Like several works");
  await page.click('nav button:has-text("Islands")');
  await expect(page.locator(".empty")).toContainText("Rate some works");
});

test("multiple floating windows coexist and reopening focuses instead of duplicating", async ({ page }) => {
  await openApp(page);

  await page.locator("tbody tr").nth(0).locator(".label-cell").click();
  await page.locator("tbody tr").nth(1).evaluate((row) => (row as HTMLElement).click());
  await expect(page.locator(".entity-window")).toHaveCount(2);

  const firstLabel = await page.locator("tbody tr").nth(0).locator(".label-cell").textContent();

  // Reopening the first entity focuses its existing window.
  await page.locator("tbody tr").nth(0).evaluate((row) => (row as HTMLElement).click());
  await expect(page.locator(".entity-window")).toHaveCount(2);

  const topWindowTitle = await page.evaluate(() => {
    const windows = [...document.querySelectorAll<HTMLElement>(".entity-window")];
    windows.sort((a, b) => Number(b.style.zIndex) - Number(a.style.zIndex));
    return windows[0]?.querySelector(".window-title strong")?.textContent;
  });
  expect(topWindowTitle).toBe(firstLabel);

  // Close controls work.
  await page.locator(".entity-window .close-button").first().click();
  await expect(page.locator(".entity-window")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(page.locator(".entity-window")).toHaveCount(0);
});

test("narrow-screen layout stays usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openApp(page);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);

  // All four tabs reachable.
  for (const label of ["Recommendations", "Evolution", "Islands", "Browse"]) {
    await page.click(`nav button:has-text("${label}")`);
  }

  // Entity window becomes a full-width sheet.
  await page.locator("tbody tr").nth(0).evaluate((row) => (row as HTMLElement).click());
  const box = await page.locator(".entity-window").boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeLessThanOrEqual(1);
  expect(box!.width).toBeGreaterThanOrEqual(388);
});

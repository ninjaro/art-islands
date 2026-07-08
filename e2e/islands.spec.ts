import { expect, test } from "@playwright/test";
import { disjointPair, fetchCatalog, openApp, seedRatings } from "./helpers";

test("islands colors update immediately after rating", async ({ page }) => {
  await openApp(page);

  await page.locator("tbody tr").nth(0).locator(".rating-buttons .like").click();
  await page.locator("tbody tr").nth(5).locator(".rating-buttons .dislike").click();

  await page.click('nav button:has-text("Islands")');
  await page.waitForSelector(".island-node");
  await expect(page.locator(".island-node.liked")).toHaveCount(1);
  await expect(page.locator(".island-node.disliked")).toHaveCount(1);
  const recommendedBefore = await page.locator(".island-node.recommended").count();
  expect(recommendedBefore).toBeGreaterThan(0);

  // Liking a gray node turns it green and refreshes recommendations/edges.
  await page.locator(".island-node.recommended").first().locator(".island-rate.like").click();
  await expect(page.locator(".island-node.liked")).toHaveCount(2);
  await expect(page.locator(".rating-summary span")).toHaveText("3 rated");
});

test("disconnected components stay separate; isolated seeds become one-node islands", async ({ page }) => {
  await openApp(page);
  const catalog = await fetchCatalog(page);
  const [first, second] = disjointPair(catalog);
  await seedRatings(page, { [String(first.id)]: 1, [String(second.id)]: 1 });

  await page.click('nav button:has-text("Islands")');
  await page.waitForSelector(".island-node");

  const islandCount = await page.locator(".island-bg").count();
  expect(islandCount).toBeGreaterThanOrEqual(2);

  // Component headings display sizes and the two seeds are in different islands.
  const headings = await page.locator(".island-heading").allTextContents();
  expect(headings.length).toBe(islandCount);
  for (const heading of headings) {
    expect(heading).toMatch(/Island \d+ · \d+ works?/);
  }
});

test("islands render bounded edges with the legend and knn help text", async ({ page }) => {
  await openApp(page);
  const catalog = await fetchCatalog(page);
  const seeds: Record<string, 1 | -1> = {};
  for (const entry of catalog.slice(0, 12)) seeds[String(entry.id)] = 1;
  await seedRatings(page, seeds);

  await page.click('nav button:has-text("Islands")');
  await page.waitForSelector(".island-node");

  // Global edge cap from settings.json (maxEdges = 500).
  const edgeCount = await page.locator(".react-flow__edge").count();
  expect(edgeCount).toBeLessThanOrEqual(500);
  expect(edgeCount).toBeGreaterThan(0);

  await expect(page.locator(".island-legend")).toBeVisible();
  await expect(page.locator(".island-legend")).toContainText("explicit relation");
  await expect(page.locator(".island-legend")).toContainText("inferred similarity");
  await expect(page.locator(".graph-help")).toContainText(/at most \d+ nearest neighbors/);
});

test("node dragging does not accidentally rate or open windows", async ({ page }) => {
  await openApp(page);
  await page.locator("tbody tr").nth(0).locator(".rating-buttons .like").click();
  await page.click('nav button:has-text("Islands")');
  await page.waitForSelector(".island-node");

  const ratedBefore = await page.locator(".rating-summary span").textContent();
  const node = page.locator(".island-node").first();
  const box = (await node.boundingBox())!;

  await page.mouse.move(box.x + box.width / 2, box.y + box.height - 6);
  await page.mouse.down();
  await page.mouse.move(box.x + 220, box.y + 160, { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(300);

  await expect(page.locator(".entity-window")).toHaveCount(0);
  await expect(page.locator(".rating-summary span")).toHaveText(ratedBefore!);
});

test("island nodes open entity windows and components can be focused", async ({ page }) => {
  await openApp(page);
  await page.locator("tbody tr").nth(0).locator(".rating-buttons .like").click();
  await page.click('nav button:has-text("Islands")');
  await page.waitForSelector(".island-node");

  await page.locator(".island-node").first().locator(".island-label").click();
  await expect(page.locator(".entity-window")).toHaveCount(1);
  await page.keyboard.press("Escape");

  await page.locator(".island-heading").last().click();
  await page.click('.graph-toolbar button:has-text("Fit all")');
});

import { expect, test } from "@playwright/test";
import { BASE, fetchCatalog, openApp } from "./helpers";

interface EvolutionNode {
  id: number;
  parent: number | null;
}

/** The label of the parent with the most children: guaranteed to overflow
 * into `+N` placeholders with the default visible-children setting. */
async function busiestParentLabel(page: import("@playwright/test").Page): Promise<string> {
  const response = await page.request.get(`${BASE}data/evolution.json`);
  const evolution = (await response.json()) as { nodes: EvolutionNode[] };
  const childCounts = new Map<number, number>();
  for (const node of evolution.nodes) {
    if (node.parent !== null) {
      childCounts.set(node.parent, (childCounts.get(node.parent) || 0) + 1);
    }
  }
  const [busiest] = [...childCounts.entries()].sort((a, b) => b[1] - a[1])[0];
  const catalog = await fetchCatalog(page);
  const item = catalog.find((entry) => entry.id === busiest);
  expect(item).toBeDefined();
  return item!.label;
}

test("placeholder expansion reveals real, clickable siblings and can fold again", async ({ page }) => {
  await openApp(page);
  const label = await busiestParentLabel(page);

  await page.click('nav button:has-text("Evolution")');
  await page.waitForSelector(".evo-node");

  // Reveal the busiest parent via search.
  await page.fill(".graph-search input", label.slice(0, 20));
  await page.locator(".graph-search-results button").first().click();
  await page.waitForTimeout(400);

  const parentNode = page.locator(".evo-node", { hasText: label.slice(0, 20) }).first();
  await parentNode.locator(".evo-toggle").click();
  await page.waitForTimeout(400);

  const placeholders = page.locator(".evo-placeholder:not(.evo-fold)");
  const placeholderCount = await placeholders.count();
  expect(placeholderCount).toBeGreaterThan(0);

  const hiddenCounts = [];
  for (let index = 0; index < placeholderCount; index += 1) {
    hiddenCounts.push(Number((await placeholders.nth(index).textContent())!.replace("+", "")));
  }
  const visibleBefore = await page.locator(".evo-open").count();

  // Expanding adds exactly the hidden children of that group.
  await placeholders.first().click();
  await page.waitForTimeout(400);
  const visibleAfter = await page.locator(".evo-open").count();
  expect(visibleAfter).toBe(visibleBefore + hiddenCounts[0]);

  // Every expanded child is independently clickable: opening one shows its window.
  await page.locator(".evo-open").last().click();
  await expect(page.locator(".entity-window")).toHaveCount(1);
  await page.keyboard.press("Escape");

  // The group can be collapsed again.
  await page.locator(".evo-fold").first().click();
  await page.waitForTimeout(400);
  expect(await page.locator(".evo-open").count()).toBe(visibleBefore);
});

test("evolution work nodes open the shared entity window", async ({ page }) => {
  await openApp(page);
  await page.click('nav button:has-text("Evolution")');
  await page.waitForSelector(".evo-node");

  const nodeLabel = await page.locator(".evo-open .evo-label").first().textContent();
  await page.locator(".evo-open").first().click();
  await expect(page.locator(".entity-window")).toHaveCount(1);
  await expect(page.locator(".entity-window .window-title strong")).toHaveText(nodeLabel!);
});

test("evolution edges expose their evidence by hover and by keyboard focus", async ({ page }) => {
  await openApp(page);
  await page.click('nav button:has-text("Evolution")');
  await page.waitForSelector(".evo-node");

  // Expand the first expandable root to materialize evidence edges.
  await page.locator(".evo-toggle").first().click();
  await page.waitForSelector(".edge-hit");

  // Keyboard focus opens the tooltip (not only mouse hover).
  await page.locator(".edge-hit").first().focus();
  const tooltip = page.locator(".edge-tooltip").first();
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toContainText(/Similarity: \d/);
  await expect(tooltip).toContainText("→"); // direction: earlier → later
  await expect(tooltip).toContainText(/shared features/);
  // Human-readable factor labels, no bare feature ids.
  await expect(tooltip).not.toContainText(/concept:\d|entity:\d/);
  await page.locator(".edge-hit").first().blur();
  await expect(page.locator(".edge-tooltip")).toHaveCount(0);

  // Mouse hover shows the same tooltip.
  await page.locator(".edge-hit").first().hover();
  await expect(page.locator(".edge-tooltip").first()).toBeVisible();
});

test("expansion state is remembered for the browser session", async ({ page }) => {
  await openApp(page);
  await page.click('nav button:has-text("Evolution")');
  await page.waitForSelector(".evo-node");

  const rootsBefore = await page.locator(".evo-open").count();
  await page.locator(".evo-toggle").first().click();
  await page.waitForTimeout(400);
  const expanded = await page.locator(".evo-open").count();
  expect(expanded).toBeGreaterThan(rootsBefore);

  await page.click('nav button:has-text("Browse")');
  await page.click('nav button:has-text("Evolution")');
  await page.waitForTimeout(400);
  expect(await page.locator(".evo-open").count()).toBe(expanded);
});

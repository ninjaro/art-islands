import { expect, test } from "@playwright/test";
import { openApp } from "./helpers";

test("browse mounts at most one page of rows and paginates", async ({ page }) => {
  await openApp(page);

  await expect(page.locator("table tbody tr")).toHaveCount(50);
  await expect(page.locator(".page-status").first()).toHaveText(/Page 1 of \d+ · [\d,]+ results/);

  await page.getByRole("button", { name: "Next page" }).first().click();
  await expect(page.locator(".page-status").first()).toHaveText(/Page 2 of/);
  await expect(page.locator("table tbody tr")).toHaveCount(50);

  await page.getByRole("button", { name: "Previous page" }).first().click();
  await expect(page.locator(".page-status").first()).toHaveText(/Page 1 of/);
});

test("changing page size remounts the right row count", async ({ page }) => {
  await openApp(page);

  await page.getByLabel("Results per page").first().selectOption("25");
  await expect(page.locator("table tbody tr")).toHaveCount(25);

  await page.getByLabel("Results per page").first().selectOption("100");
  await expect(page.locator("table tbody tr")).toHaveCount(100);
});

test("filtering searches the whole catalog and resets to page 1", async ({ page }) => {
  await openApp(page);

  // Navigate away from page 1 first.
  await page.getByRole("button", { name: "Next page" }).first().click();
  await page.getByRole("button", { name: "Next page" }).first().click();
  await expect(page.locator(".page-status").first()).toHaveText(/Page 3 of/);

  // The filter applies to the complete dataset, not the mounted page.
  await page.getByLabel("Search works, concepts, and contributors").fill("nosferatu");
  await expect(page.locator(".page-status").first()).toHaveText(/Page 1 of/);
  await expect(page.locator("td.label-cell", { hasText: /Nosferatu/i }).first()).toBeVisible();

  // Active filter chip appears and can clear the filter.
  await expect(page.locator(".filter-chip")).toHaveCount(1);
  await page.getByRole("button", { name: /Remove filter Search/ }).click();
  await expect(page.locator(".filter-chip")).toHaveCount(0);
});

test("pagination state survives switching views", async ({ page }) => {
  await openApp(page);

  await page.getByRole("button", { name: "Next page" }).first().click();
  await expect(page.locator(".page-status").first()).toHaveText(/Page 2 of/);

  await page.click('nav button:has-text("Islands")');
  await page.click('nav button:has-text("Browse")');
  await expect(page.locator(".page-status").first()).toHaveText(/Page 2 of/);
});

test("relevance sort is only available with a search context and ranks matches", async ({ page }) => {
  await openApp(page);

  const relevanceOption = page.locator('select[aria-label="Sort"] option[value="relevance"]');
  await expect(relevanceOption).toBeDisabled();

  await page.getByLabel("Search works, concepts, and contributors").fill("horror");
  await expect(relevanceOption).toBeEnabled();
  await page.getByLabel("Sort").selectOption("relevance");
  await expect(page.locator("table tbody tr").first()).toBeVisible();

  // Clearing filters restores the literal date sort.
  await page.getByRole("button", { name: "Clear all" }).click();
  await expect(page.getByLabel("Sort")).toHaveValue("date");
});

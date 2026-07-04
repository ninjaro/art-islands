import type { Page } from "@playwright/test";

export const BASE = "/art-islands/";

export async function openApp(page: Page): Promise<void> {
  await page.goto(BASE);
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.reload();
  await page.waitForSelector("table tbody tr");
}

export async function seedRatings(page: Page, ratings: Record<string, 1 | -1>): Promise<void> {
  await page.evaluate(
    (value) => localStorage.setItem("art-islands-ratings-v1", JSON.stringify(value)),
    ratings,
  );
  await page.reload();
  await page.waitForSelector("table tbody tr");
}

export interface CatalogEntry {
  id: number;
  label: string;
  date: string | null;
  tags: [number, number, number][];
}

export async function fetchCatalog(page: Page): Promise<CatalogEntry[]> {
  const response = await page.request.get(`${BASE}data/catalog.json`);
  return (await response.json()) as CatalogEntry[];
}

/** Two catalog works with no shared tags: guaranteed disconnected seeds. */
export function disjointPair(catalog: CatalogEntry[]): [CatalogEntry, CatalogEntry] {
  const first = catalog[0];
  const firstTags = new Set(first.tags.map(([tagId]) => tagId));
  for (const candidate of catalog) {
    if (candidate.id === first.id) continue;
    if (!candidate.tags.some(([tagId]) => firstTags.has(tagId))) {
      return [first, candidate];
    }
  }
  throw new Error("no disjoint pair found in catalog");
}

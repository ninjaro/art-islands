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
  conceptIds: Set<number>;
  hasDuration: boolean;
  contributorRoles: string[];
}

export async function fetchCatalog(page: Page): Promise<CatalogEntry[]> {
  const [catalogResponse, conceptsResponse] = await Promise.all([
    page.request.get(`${BASE}data/v2/catalog.json`),
    page.request.get(`${BASE}data/v2/concepts.json`),
  ]);
  const catalog = (await catalogResponse.json()) as Array<{
    id: number;
    label: string;
    compatibilityDate?: string;
    measurements?: Array<{ type: string }>;
    contributors?: Record<string, number[]>;
  }>;
  const concepts = (await conceptsResponse.json()) as {
    entityConcepts: Array<{ entityId: number; conceptId: number }>;
  };
  const conceptsByEntity = new Map<number, Set<number>>();
  for (const row of concepts.entityConcepts) {
    let set = conceptsByEntity.get(row.entityId);
    if (!set) conceptsByEntity.set(row.entityId, (set = new Set()));
    set.add(row.conceptId);
  }
  return catalog.map((item) => ({
    id: item.id,
    label: item.label,
    date: item.compatibilityDate ?? null,
    conceptIds: conceptsByEntity.get(item.id) ?? new Set(),
    hasDuration: (item.measurements ?? []).some((measurement) => measurement.type === "duration"),
    contributorRoles: Object.keys(item.contributors ?? {}),
  }));
}

/** Two catalog works with no shared concepts: guaranteed disconnected seeds. */
export function disjointPair(catalog: CatalogEntry[]): [CatalogEntry, CatalogEntry] {
  const first = catalog[0];
  for (const candidate of catalog) {
    if (candidate.id === first.id) continue;
    let shares = false;
    for (const conceptId of candidate.conceptIds) {
      if (first.conceptIds.has(conceptId)) {
        shares = true;
        break;
      }
    }
    if (!shares) return [first, candidate];
  }
  throw new Error("no disjoint pair found in catalog");
}

import type { AppData, CatalogItem, EvolutionExport, Lookup, Settings, Tag } from "./types";
import { DEFAULT_SETTINGS, mergeSettings } from "./types";

/** All fetch paths derive from the Vite base URL so the app works under /art-islands/. */
export const BASE_URL: string = import.meta.env.BASE_URL;

export function dataUrl(name: string): string {
  return `${BASE_URL}data/${name}`;
}

async function loadJson<T>(name: string): Promise<T> {
  const response = await fetch(dataUrl(name));
  if (!response.ok) {
    throw new Error(`${dataUrl(name)}: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

async function loadOptionalJson<T>(name: string): Promise<T | null> {
  try {
    const response = await fetch(dataUrl(name));
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function loadSettings(): Promise<Settings> {
  const raw = await loadOptionalJson<unknown>("settings.json");
  return raw === null ? DEFAULT_SETTINGS : mergeSettings(raw);
}

export async function loadAppData(): Promise<{ data: AppData; settings: Settings }> {
  const [catalog, tags, lookup, evolution, settings] = await Promise.all([
    loadJson<CatalogItem[]>("catalog.json"),
    loadJson<Tag[]>("tags.json"),
    loadJson<Lookup>("entities-lookup.json"),
    loadOptionalJson<EvolutionExport>("evolution.json"),
    loadSettings(),
  ]);
  return {
    data: {
      catalog,
      catalogById: new Map(catalog.map((item) => [item.id, item])),
      tags,
      tagById: new Map(tags.map((tag) => [tag.id, tag])),
      lookup,
      evolution,
    },
    settings,
  };
}

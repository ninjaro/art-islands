import type { AppData, CatalogItem, EvolutionExport, Lookup, Settings, Tag, V2Data } from "./types";
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

export async function loadV2Data(): Promise<V2Data | null> {
  const [catalog, entities, entityTypes, relations, concepts, advisories, ratings, restrictions] = await Promise.all([
    loadOptionalJson<V2Data["catalog"]>("v2/catalog.json"),
    loadOptionalJson<V2Data["entities"]>("v2/entities.json"),
    loadOptionalJson<V2Data["entityTypes"]>("v2/entity-types.json"),
    loadOptionalJson<V2Data["relations"]>("v2/relations.json"),
    loadOptionalJson<V2Data["concepts"]>("v2/concepts.json"),
    loadOptionalJson<V2Data["advisories"]>("v2/advisories.json"),
    loadOptionalJson<V2Data["ratings"]>("v2/ratings.json"),
    loadOptionalJson<V2Data["restrictions"]>("v2/restrictions.json"),
  ]);
  if (!catalog || !entities || !entityTypes || !relations || !concepts) return null;
  return {
    catalog,
    entities,
    entityTypes,
    relations,
    concepts,
    advisories: advisories || [],
    ratings: ratings || [],
    restrictions: restrictions || [],
  };
}

export async function loadAppData(): Promise<{ data: AppData; settings: Settings }> {
  const [catalog, tags, lookup, evolution, settings, v2] = await Promise.all([
    loadJson<CatalogItem[]>("catalog.json"),
    loadJson<Tag[]>("tags.json"),
    loadJson<Lookup>("entities-lookup.json"),
    loadOptionalJson<EvolutionExport>("evolution.json"),
    loadSettings(),
    loadV2Data(),
  ]);
  return {
    data: {
      catalog,
      catalogById: new Map(catalog.map((item) => [item.id, item])),
      tags,
      tagById: new Map(tags.map((tag) => [tag.id, tag])),
      lookup,
      evolution,
      v2,
    },
    settings,
  };
}

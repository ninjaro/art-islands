import { buildDomainModel } from "./domain";
import type { AppData, EvolutionExport, Settings, V2Data } from "./types";
import { DEFAULT_SETTINGS, EVOLUTION_EXPORT_VERSION, mergeSettings } from "./types";

/** All fetch paths derive from the Vite base URL so the app works under /art-islands/. */
export const BASE_URL: string = import.meta.env.BASE_URL;

export function dataUrl(name: string): string {
  return `${BASE_URL}data/${name}`;
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

interface V2Parts {
  catalog: unknown;
  entities: unknown;
  entityTypes: unknown;
  relations: unknown;
  concepts: unknown;
  advisories: unknown;
  restrictions: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export type V2Validation = { data: V2Data } | { missing: string[]; invalid: string[] };

/**
 * Structural validation of the required V2 exports. Required files that are
 * absent or the wrong shape fail loudly; optional files (advisories and
 * restrictions) fall back to valid empty states.
 */
export function validateV2Data(parts: V2Parts): V2Validation {
  const missing: string[] = [];
  const invalid: string[] = [];

  const check = (name: string, value: unknown, valid: boolean) => {
    if (value === null || value === undefined) missing.push(`v2/${name}.json`);
    else if (!valid) invalid.push(`v2/${name}.json`);
  };

  check("catalog", parts.catalog, Array.isArray(parts.catalog));
  check("entities", parts.entities, isRecord(parts.entities));
  check(
    "entity-types",
    parts.entityTypes,
    isRecord(parts.entityTypes) &&
      Array.isArray((parts.entityTypes as Record<string, unknown>).definitions) &&
      Array.isArray((parts.entityTypes as Record<string, unknown>).assignments),
  );
  check("relations", parts.relations, Array.isArray(parts.relations));
  check(
    "concepts",
    parts.concepts,
    isRecord(parts.concepts) &&
      Array.isArray((parts.concepts as Record<string, unknown>).categories) &&
      Array.isArray((parts.concepts as Record<string, unknown>).concepts) &&
      Array.isArray((parts.concepts as Record<string, unknown>).entityConcepts),
  );

  if (parts.advisories !== null && parts.advisories !== undefined) {
    if (!isRecord(parts.advisories) || !Array.isArray((parts.advisories as Record<string, unknown>).advisories)) {
      invalid.push("v2/advisories.json");
    }
  }
  if (parts.restrictions !== null && parts.restrictions !== undefined && !Array.isArray(parts.restrictions)) {
    invalid.push("v2/restrictions.json");
  }

  if (missing.length || invalid.length) return { missing, invalid };

  const data: V2Data = {
    catalog: parts.catalog as V2Data["catalog"],
    entities: parts.entities as V2Data["entities"],
    entityTypes: parts.entityTypes as V2Data["entityTypes"],
    relations: parts.relations as V2Data["relations"],
    concepts: parts.concepts as V2Data["concepts"],
    advisories: (parts.advisories as V2Data["advisories"]) ?? { categories: [], advisories: [] },
    restrictions: (parts.restrictions as V2Data["restrictions"]) ?? [],
  };
  return { data };
}

export async function loadAppData(): Promise<{ data: AppData; settings: Settings }> {
  const [catalog, entities, entityTypes, relations, concepts, advisories, restrictions, evolution, settings] =
    await Promise.all([
      loadOptionalJson<unknown>("v2/catalog.json"),
      loadOptionalJson<unknown>("v2/entities.json"),
      loadOptionalJson<unknown>("v2/entity-types.json"),
      loadOptionalJson<unknown>("v2/relations.json"),
      loadOptionalJson<unknown>("v2/concepts.json"),
      loadOptionalJson<unknown>("v2/advisories.json"),
      loadOptionalJson<unknown>("v2/restrictions.json"),
      loadOptionalJson<EvolutionExport>("evolution.json"),
      loadSettings(),
    ]);

  const validation = validateV2Data({
    catalog,
    entities,
    entityTypes,
    relations,
    concepts,
    advisories,
    restrictions,
  });
  if (!("data" in validation)) {
    const problems = [
      ...validation.missing.map((name) => `missing ${name}`),
      ...validation.invalid.map((name) => `invalid ${name}`),
    ];
    throw new Error(
      `The V2 data exports are missing or invalid (${problems.join(", ")}). ` +
        "Regenerate them with: .venv/bin/art-islands export && .venv/bin/art-islands db-v2 export",
    );
  }

  // A stale (version 1) evolution export shows the regeneration hint instead of crashing.
  const usableEvolution = evolution && evolution.version === EVOLUTION_EXPORT_VERSION ? evolution : null;

  return {
    data: {
      v2: validation.data,
      domain: buildDomainModel(validation.data),
      evolution: usableEvolution,
    },
    settings,
  };
}

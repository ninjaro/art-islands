import type { BroadKind, DomainModel, WorkViewModel } from "./domain";
import type { V2Relation } from "./types";

export interface WorkSpec {
  label?: string;
  date?: string | null;
  broadKind?: BroadKind;
  concepts?: Array<{ id: number; label?: string; category?: string; weight: number | null; polarity?: number }>;
  contributors?: Array<{
    entityId: number;
    label?: string;
    role: string;
    family?: string;
    weight: number;
    polarity?: number;
  }>;
  advisories?: Array<{ categoryCode: string; category?: string; intensity?: number }>;
}

/** Minimal WorkViewModel for algorithm tests. */
export function makeWork(id: number, spec: WorkSpec = {}): WorkViewModel {
  const concepts = (spec.concepts ?? []).map((concept) => ({
    conceptId: concept.id,
    label: concept.label ?? `Concept ${concept.id}`,
    category: "genre",
    categoryLabel: concept.category ?? "Genre",
    weight: concept.weight,
    polarity: concept.polarity ?? 0,
  }));
  const contributors = (spec.contributors ?? [])
    .map((contributor) => ({
      entityId: contributor.entityId,
      label: contributor.label ?? `Entity ${contributor.entityId}`,
      role: contributor.role,
      roleLabel: contributor.role,
      family: contributor.family ?? "person",
      weight: contributor.weight,
      polarity: contributor.polarity ?? 0,
    }))
    .sort((a, b) => a.role.localeCompare(b.role));
  const advisories = (spec.advisories ?? []).map((advisory) => ({
    categoryCode: advisory.categoryCode,
    category: advisory.category ?? advisory.categoryCode,
    intensity: advisory.intensity,
  }));
  const date = spec.date ?? null;
  return {
    id,
    label: spec.label ?? `Work ${id}`,
    family: "work",
    type: "film",
    typeLabel: "Film",
    broadKind: spec.broadKind ?? "film",
    dates: [],
    sortDate: date,
    year: date ? Number(date.slice(0, 4)) : null,
    concepts,
    conceptsByCategory: {},
    contributors,
    contributorsByRole: {},
    measurements: [],
    advisories,
    restrictions: [],
    identifiers: [],
  };
}

/** Minimal DomainModel wrapper for algorithm tests. */
export function makeDomain(works: WorkViewModel[], workRelations: V2Relation[] = []): DomainModel {
  return {
    works,
    workById: new Map(works.map((work) => [work.id, work])),
    entityById: new Map(),
    conceptById: new Map(),
    conceptCategories: [],
    typeOptions: [],
    workRelations,
  };
}

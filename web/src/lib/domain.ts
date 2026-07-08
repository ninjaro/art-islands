import { formatDuration, identifierUrl, schemeLabel } from "./format";
import type { V2Concept, V2Data, V2Entity, V2Relation } from "./types";

export type BroadKind = "film" | "tv" | "music" | "game" | "work";

export interface NormalizedDate {
  type: string;
  value: string;
  precision: number;
  primary: boolean;
}

export interface NormalizedConceptAssignment {
  conceptId: number;
  label: string;
  description?: string;
  category: string;
  categoryLabel: string;
  weight: number | null;
  polarity: number;
}

export interface NormalizedContributor {
  entityId: number;
  label: string;
  role: string;
  roleLabel: string;
  family: string;
  characterLabel?: string;
  weight: number;
  polarity: number;
}

export interface NormalizedMeasurement {
  type: string;
  number?: number;
  text?: string;
  unit?: string;
  qualifier?: string;
}

export interface NormalizedDuration {
  seconds: number;
  label: string;
}

export interface NormalizedAdvisory {
  categoryCode: string;
  category: string;
  intensity?: number;
  uncertainty?: number;
  description?: string;
}

export interface NormalizedRestriction {
  type: string;
  countryCode?: string;
  region?: string;
  reason?: string;
  status?: string;
  startDate?: string;
  endDate?: string;
  edition?: string;
}

export interface NormalizedIdentifier {
  scheme: string;
  label: string;
  value: string;
  url: string;
  primary: boolean;
}

export interface WorkViewModel {
  id: number;
  label: string;
  description?: string;
  family: string;
  type: string;
  typeLabel: string;
  broadKind: BroadKind;
  image?: string;

  dates: NormalizedDate[];
  primaryDate?: NormalizedDate;
  sortDate: string | null;
  year: number | null;

  concepts: NormalizedConceptAssignment[];
  conceptsByCategory: Record<string, NormalizedConceptAssignment[]>;

  contributors: NormalizedContributor[];
  contributorsByRole: Record<string, NormalizedContributor[]>;

  measurements: NormalizedMeasurement[];
  duration?: NormalizedDuration;

  advisories: NormalizedAdvisory[];
  restrictions: NormalizedRestriction[];

  identifiers: NormalizedIdentifier[];
}

export interface DomainModel {
  works: WorkViewModel[];
  workById: Map<number, WorkViewModel>;
  entityById: Map<number, V2Entity>;
  conceptById: Map<number, V2Concept>;
  conceptCategories: { code: string; label: string }[];
  typeOptions: { code: string; label: string; count: number }[];
  /** Relations whose source and target are both catalogued works. */
  workRelations: V2Relation[];
}

const ROLE_LABELS: Record<string, string> = {
  director: "Director",
  creator: "Creator",
  author: "Author",
  screenwriter: "Screenwriter",
  cast_member: "Cast",
  voice_actor: "Voice cast",
  performer: "Performer",
  composer: "Composer",
  lyricist: "Lyricist",
  music_artist: "Artist",
  producer: "Producer",
  production_company: "Production company",
  record_label: "Record label",
  distributor: "Distributor",
  publisher: "Publisher",
  broadcaster: "Broadcaster",
  adapted_from: "Adapted from",
  influenced_by: "Influenced by",
  inspired_by: "Inspired by",
  influenced: "Influenced",
  main_subject: "Subject",
  depicts: "Depicts",
};

export function roleLabel(code: string): string {
  return ROLE_LABELS[code] ?? code.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function broadKindForType(code: string): BroadKind {
  if (code === "film") return "film";
  if (code === "television_series") return "tv";
  if (code === "music_album" || code === "musical_work") return "music";
  if (code === "video_game") return "game";
  return "work";
}

const FALLBACK_TYPE = { code: "other_creative_work", label: "Work" };

function groupBy<T>(items: T[], keyOf: (item: T) => number): Map<number, T[]> {
  const groups = new Map<number, T[]>();
  for (const item of items) {
    const key = keyOf(item);
    let group = groups.get(key);
    if (!group) groups.set(key, (group = []));
    group.push(item);
  }
  return groups;
}

export function buildDomainModel(v2: V2Data): DomainModel {
  const entityById = new Map<number, V2Entity>();
  for (const entity of Object.values(v2.entities)) entityById.set(entity.id, entity);

  const conceptById = new Map<number, V2Concept>(v2.concepts.concepts.map((concept) => [concept.id, concept]));
  const categoryLabels = new Map<string, string>(
    v2.concepts.categories.map((category) => [category.code, category.label]),
  );

  const typeById = new Map(v2.entityTypes.definitions.map((definition) => [definition.id, definition]));
  const primaryTypeByEntity = new Map<number, { code: string; label: string }>();
  for (const assignment of v2.entityTypes.assignments) {
    if (!assignment.isPrimary || primaryTypeByEntity.has(assignment.entityId)) continue;
    const definition = typeById.get(assignment.typeId);
    if (definition) primaryTypeByEntity.set(assignment.entityId, { code: definition.code, label: definition.label });
  }

  const conceptsByEntity = groupBy(v2.concepts.entityConcepts, (row) => row.entityId);
  const relationsBySource = groupBy(v2.relations, (relation) => relation.source);
  const advisoriesByEntity = groupBy(v2.advisories.advisories, (advisory) => advisory.entityId);
  const advisoryCategoryLabels = new Map(v2.advisories.categories.map((category) => [category.code, category.label]));
  const restrictionsByEntity = groupBy(v2.restrictions, (restriction) => restriction.entityId);

  const catalogIds = new Set(v2.catalog.map((item) => item.id));
  const works: WorkViewModel[] = [];

  for (const item of v2.catalog) {
    const entity = entityById.get(item.id);

    const dates: NormalizedDate[] = (item.dates ?? []).map((date) => ({
      type: date.type,
      value: date.value,
      precision: date.precision,
      primary: Boolean(date.primary),
    }));
    let primaryDate = dates.find((date) => date.primary) ?? dates[0];
    if (!primaryDate && item.compatibilityDate) {
      primaryDate = {
        type: "compatibility",
        value: item.compatibilityDate,
        precision: item.compatibilityDatePrecision ?? 3,
        primary: true,
      };
      dates.push(primaryDate);
    }
    const sortDate = primaryDate?.value ?? null;
    const parsedYear = sortDate ? Number(sortDate.slice(0, 4)) : NaN;
    const year = Number.isFinite(parsedYear) ? parsedYear : null;

    const concepts: NormalizedConceptAssignment[] = [];
    for (const row of conceptsByEntity.get(item.id) ?? []) {
      const concept = conceptById.get(row.conceptId);
      if (!concept) continue;
      const category = categoryLabels.has(concept.category) ? concept.category : "other";
      concepts.push({
        conceptId: row.conceptId,
        label: concept.label,
        description: concept.description,
        category,
        categoryLabel: categoryLabels.get(category) ?? "Other",
        weight: row.weight,
        polarity: row.polarity,
      });
    }
    concepts.sort(
      (a, b) =>
        Number(a.weight === null) - Number(b.weight === null) ||
        (b.weight ?? -1) - (a.weight ?? -1) ||
        a.label.localeCompare(b.label) ||
        a.conceptId - b.conceptId,
    );
    const conceptsByCategory: Record<string, NormalizedConceptAssignment[]> = {};
    for (const concept of concepts) {
      (conceptsByCategory[concept.category] ??= []).push(concept);
    }

    const contributors: NormalizedContributor[] = [];
    for (const relation of relationsBySource.get(item.id) ?? []) {
      const target = entityById.get(relation.target);
      contributors.push({
        entityId: relation.target,
        label: target?.label ?? `Entity ${relation.target}`,
        role: relation.type,
        roleLabel: roleLabel(relation.type),
        family: target?.family ?? "unknown",
        weight: relation.weight,
        polarity: relation.polarity ?? 0,
      });
    }
    contributors.sort(
      (a, b) =>
        a.role.localeCompare(b.role) || b.weight - a.weight || a.label.localeCompare(b.label) || a.entityId - b.entityId,
    );
    const contributorsByRole: Record<string, NormalizedContributor[]> = {};
    for (const contributor of contributors) {
      (contributorsByRole[contributor.role] ??= []).push(contributor);
    }

    const measurements: NormalizedMeasurement[] = (item.measurements ?? []).map((measurement) => ({
      type: measurement.type,
      number: measurement.number,
      text: measurement.text,
      unit: measurement.unit,
      qualifier: measurement.qualifier,
    }));
    let duration: NormalizedDuration | undefined;
    const durationRow = measurements.find((measurement) => measurement.type === "duration");
    if (durationRow?.number !== undefined) {
      const seconds =
        durationRow.unit === "minutes"
          ? durationRow.number * 60
          : durationRow.unit === "hours"
            ? durationRow.number * 3600
            : durationRow.number;
      duration = { seconds, label: formatDuration(seconds) };
    }

    const advisories: NormalizedAdvisory[] = (advisoriesByEntity.get(item.id) ?? [])
      .map((advisory) => ({
        categoryCode: advisory.categoryCode,
        category: advisoryCategoryLabels.get(advisory.categoryCode) ?? "Content",
        intensity: advisory.intensity ?? undefined,
        uncertainty: advisory.uncertainty ?? undefined,
        description: advisory.description ?? undefined,
      }))
      .sort((a, b) => (b.intensity ?? 0) - (a.intensity ?? 0) || a.category.localeCompare(b.category));

    const restrictions: NormalizedRestriction[] = (restrictionsByEntity.get(item.id) ?? []).map((restriction) => ({
      type: restriction.restrictionType,
      countryCode: restriction.countryCode,
      region: restriction.regionLabel,
      reason: restriction.reason,
      status: restriction.status,
      startDate: restriction.startDate,
      endDate: restriction.endDate,
      edition: restriction.editionLabel,
    }));

    const identifiers: NormalizedIdentifier[] = [];
    const seenIdentifiers = new Set<string>();
    for (const identifier of entity?.identifiers ?? []) {
      const key = `${identifier.scheme}:${identifier.value}`;
      if (seenIdentifiers.has(key)) continue;
      seenIdentifiers.add(key);
      identifiers.push({
        scheme: identifier.scheme,
        label: schemeLabel(identifier.scheme),
        value: identifier.value,
        url: identifierUrl(identifier.scheme, identifier.value),
        primary: identifier.primary,
      });
    }
    identifiers.sort(
      (a, b) => Number(b.primary) - Number(a.primary) || a.label.localeCompare(b.label) || a.value.localeCompare(b.value),
    );

    const type = primaryTypeByEntity.get(item.id) ?? FALLBACK_TYPE;
    works.push({
      id: item.id,
      label: item.label,
      description: entity?.description,
      family: item.family ?? "work",
      type: type.code,
      typeLabel: type.label,
      broadKind: broadKindForType(type.code),
      image: item.image,
      dates,
      primaryDate,
      sortDate,
      year,
      concepts,
      conceptsByCategory,
      contributors,
      contributorsByRole,
      measurements,
      duration,
      advisories,
      restrictions,
      identifiers,
    });
  }

  const typeCounts = new Map<string, { label: string; count: number }>();
  for (const work of works) {
    const entry = typeCounts.get(work.type);
    if (entry) entry.count += 1;
    else typeCounts.set(work.type, { label: work.typeLabel, count: 1 });
  }
  const typeOptions = [...typeCounts.entries()]
    .map(([code, { label, count }]) => ({ code, label, count }))
    .sort((a, b) => a.label.localeCompare(b.label));

  const workRelations = v2.relations.filter(
    (relation) => catalogIds.has(relation.source) && catalogIds.has(relation.target),
  );

  return {
    works,
    workById: new Map(works.map((work) => [work.id, work])),
    entityById,
    conceptById,
    conceptCategories: v2.concepts.categories.map(({ code, label }) => ({ code, label })),
    typeOptions,
    workRelations,
  };
}

export type RatingValue = 1 | -1;
export type Ratings = Record<string, RatingValue>;

export interface RecommendationSettings {
  likeWeight: number;
  dislikeWeight: number;
  limit: number;
}

export interface FeatureSettings {
  directConceptMultiplier: number;
  creatorMultiplier: number;
  directorMultiplier: number;
  authorMultiplier: number;
  producerMultiplier: number;
  performerMultiplier: number;
  organizationMultiplier: number;
  contentGuideMultiplier: number;
}

export interface EvolutionSettings {
  visibleChildrenPerNode: number;
  maxInitialRoots: number;
  groupingSimilarity: number;
  minimumSimilarity: number;
  minimumSharedFeatures: number;
  kindMismatchFactor: number;
}

export interface IslandsSettings {
  maxRecommendationNodes: number;
  maxInferredNeighborsPerNode: number;
  maxEdges: number;
  minimumSimilarity: number;
}

export interface BrowseSettings {
  defaultPageSize: number;
  pageSizeOptions: number[];
}

export interface Settings {
  recommendation: RecommendationSettings;
  features: FeatureSettings;
  evolution: EvolutionSettings;
  islands: IslandsSettings;
  browse: BrowseSettings;
}

export const DEFAULT_SETTINGS: Settings = {
  recommendation: {
    likeWeight: 1.0,
    dislikeWeight: 1.5,
    limit: 100,
  },
  features: {
    directConceptMultiplier: 1.0,
    creatorMultiplier: 0.55,
    directorMultiplier: 0.5,
    authorMultiplier: 0.55,
    producerMultiplier: 0.3,
    performerMultiplier: 0.25,
    organizationMultiplier: 0.2,
    contentGuideMultiplier: 0.25,
  },
  evolution: {
    visibleChildrenPerNode: 4,
    maxInitialRoots: 20,
    groupingSimilarity: 0.25,
    minimumSimilarity: 0.18,
    minimumSharedFeatures: 2,
    kindMismatchFactor: 0.6,
  },
  islands: {
    maxRecommendationNodes: 150,
    maxInferredNeighborsPerNode: 8,
    maxEdges: 500,
    minimumSimilarity: 0.12,
  },
  browse: {
    defaultPageSize: 50,
    pageSizeOptions: [25, 50, 100],
  },
};

/** Evidence supporting one inferred graph edge (evolution or islands). */
export interface EdgeEvidence {
  score: number;
  sharedFeatureCount: number;
  topFactors: import("./features").EdgeFactor[];
}

/** One inferred lineage record from the build-time export (version 2). */
export interface EvolutionNode {
  /** Entity id of the work. */
  id: number;
  /** Entity id of the inferred earlier work, or null for roots. */
  parent: number | null;
  /** Evidence supporting the inferred parent edge. */
  evidence: EdgeEvidence;
}

export interface EvolutionExport {
  version: number;
  note: string;
  nodes: EvolutionNode[];
}

export const EVOLUTION_EXPORT_VERSION = 2;

export interface V2Identifier {
  scheme: string;
  value: string;
  primary: boolean;
}

export interface V2Entity {
  id: number;
  label: string;
  description?: string;
  family?: "work" | "person" | "group" | "organization" | "place" | "concept" | "unknown";
  image?: string;
  catalogued: boolean;
  identifiers?: V2Identifier[];
}

export interface V2Date {
  type: string;
  value: string;
  precision: number;
  endValue?: string;
  endPrecision?: number;
  edition?: string;
  rank?: string;
  primary?: boolean;
  confidence?: number;
}

export interface V2Measurement {
  type: string;
  number?: number;
  text?: string;
  unit?: string;
  qualifier?: string;
  confidence?: number;
}

export interface V2CatalogItem {
  id: number;
  label: string;
  family?: string;
  image?: string;
  compatibilityDate?: string;
  compatibilityDatePrecision?: number;
  dates?: V2Date[];
  contributors?: Record<string, number[]>;
  concepts?: Record<string, number[]>;
  measurements?: V2Measurement[];
}

export interface V2EntityTypeDefinition {
  id: number;
  code: string;
  family: string;
  label: string;
  description: string | null;
}

export interface V2EntityTypeAssignment {
  entityId: number;
  typeId: number;
  isPrimary: number;
  confidence: number | null;
}

export interface V2Relation {
  id: number;
  source: number;
  target: number;
  type: string;
  weight: number;
  polarity?: number;
  confidence?: number;
}

export interface V2Concept {
  id: number;
  label: string;
  description?: string;
  category: string;
  namespace?: string;
  value?: string;
  confidence?: number;
}

export interface V2EntityConcept {
  entityId: number;
  conceptId: number;
  weight: number | null;
  polarity: number;
  confidence: number | null;
}

export interface V2ConceptExport {
  categories: { id: number; code: string; label: string }[];
  concepts: V2Concept[];
  entityConcepts: V2EntityConcept[];
}

export interface V2AdvisoryCategory {
  code: string;
  label: string;
  description?: string | null;
}

export interface V2Advisory {
  entityId: number;
  categoryCode: string;
  scaleVersion?: string | null;
  medium?: string | null;
  intensity?: number | null;
  centrality?: number | null;
  explicitness?: number | null;
  realism?: number | null;
  recurrence?: number | null;
  sensoryImpact?: number | null;
  coercion?: number | null;
  avoidancePriority?: number | null;
  narrativeProximity?: number | null;
  languageDependency?: number | null;
  guidanceLevel?: string | null;
  contentRole?: string | null;
  stance?: string | null;
  genreContext?: string | null;
  confidence?: number | null;
  uncertainty?: number | null;
  description?: string | null;
  dimensionValuesJson?: string | null;
  contextJson?: string | null;
}

export interface V2AdvisoryExport {
  categories: V2AdvisoryCategory[];
  advisories: V2Advisory[];
}

export interface V2Restriction {
  id: number;
  entityId: number;
  countryCode?: string;
  regionLabel?: string;
  restrictionType: string;
  startDate?: string;
  endDate?: string;
  reason?: string;
  editionLabel?: string;
  status?: string;
}

export interface V2Data {
  catalog: V2CatalogItem[];
  entities: Record<string, V2Entity>;
  entityTypes: {
    definitions: V2EntityTypeDefinition[];
    assignments: V2EntityTypeAssignment[];
  };
  relations: V2Relation[];
  concepts: V2ConceptExport;
  advisories: V2AdvisoryExport;
  restrictions: V2Restriction[];
}

export interface AppData {
  v2: V2Data;
  domain: import("./domain").DomainModel;
  /** Optional build-time lineage export; views show a regeneration hint when absent. */
  evolution: EvolutionExport | null;
}

const LEGACY_SETTING_ALIASES: Record<string, Record<string, string>> = {
  islands: { maxNeighborsPerSeed: "maxInferredNeighborsPerNode" },
  evolution: { minimumSharedTags: "minimumSharedFeatures" },
};

export function mergeSettings(raw: unknown): Settings {
  const source = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const merged = structuredClone(DEFAULT_SETTINGS) as unknown as Record<string, Record<string, unknown>>;
  for (const sectionName of Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[]) {
    const section = source[sectionName];
    if (!section || typeof section !== "object") continue;
    const incoming: Record<string, unknown> = { ...(section as Record<string, unknown>) };
    for (const [legacy, current] of Object.entries(LEGACY_SETTING_ALIASES[sectionName] ?? {})) {
      if (incoming[current] === undefined && incoming[legacy] !== undefined) incoming[current] = incoming[legacy];
      delete incoming[legacy];
    }
    const target = merged[sectionName];
    for (const [name, value] of Object.entries(incoming)) {
      if (!(name in target)) continue;
      if (Array.isArray(target[name])) {
        const list = Array.isArray(value)
          ? value.map(Number).filter((entry) => Number.isInteger(entry) && entry > 0)
          : [];
        if (list.length && Array.isArray(value) && list.length === value.length) target[name] = list;
      } else {
        const num = Number(value);
        if (Number.isFinite(num) && num >= 0) target[name] = num;
      }
    }
  }
  const result = merged as unknown as Settings;
  result.recommendation.limit = Math.max(1, Math.floor(result.recommendation.limit));
  if (!result.browse.pageSizeOptions.includes(result.browse.defaultPageSize)) {
    result.browse.defaultPageSize = result.browse.pageSizeOptions.includes(DEFAULT_SETTINGS.browse.defaultPageSize)
      ? DEFAULT_SETTINGS.browse.defaultPageSize
      : result.browse.pageSizeOptions[0];
  }
  return result;
}

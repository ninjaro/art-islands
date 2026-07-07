/** [tagId, weight 0-100, polarity -1|0|1] */
export type TagEntry = [number, number, number];

/** [targetEntityId, linkKind, weight 0-100, polarity -1|0|1] */
export type LinkEntry = [number, number, number, number];

/** [refKindLabel, refValue] */
export type RefEntry = [string, string];

export interface CatalogItem {
  id: number;
  label: string;
  kind: number;
  date: string | null;
  datePrecision: number;
  image: string | null;
  refs: RefEntry[];
  tags: TagEntry[];
  links: LinkEntry[];
}

export interface Tag {
  id: number;
  name: string;
  description: string | null;
  kind: number;
  namespace: string | null;
  value: string | null;
}

export interface LookupEntry {
  label: string;
  kind: number;
  catalogued: boolean;
}

export type Lookup = Record<string, LookupEntry>;

export type RatingValue = 1 | -1;
export type Ratings = Record<string, RatingValue>;

export interface RecommendationSettings {
  likeWeight: number;
  dislikeWeight: number;
  limit: number;
}

export interface EvolutionSettings {
  visibleChildrenPerNode: number;
  maxInitialRoots: number;
  groupingSimilarity: number;
  minimumSimilarity: number;
  minimumSharedTags: number;
}

export interface IslandsSettings {
  maxRecommendationNodes: number;
  maxNeighborsPerSeed: number;
  maxEdges: number;
  minimumSimilarity: number;
}

export interface Settings {
  recommendation: RecommendationSettings;
  evolution: EvolutionSettings;
  islands: IslandsSettings;
}

export const DEFAULT_SETTINGS: Settings = {
  recommendation: {
    likeWeight: 1.0,
    dislikeWeight: 1.5,
    limit: 100,
  },
  evolution: {
    visibleChildrenPerNode: 4,
    maxInitialRoots: 20,
    groupingSimilarity: 0.25,
    minimumSimilarity: 0.18,
    minimumSharedTags: 2,
  },
  islands: {
    maxRecommendationNodes: 150,
    maxNeighborsPerSeed: 12,
    maxEdges: 500,
    minimumSimilarity: 0.12,
  },
};

/** One inferred lineage record from the build-time export. */
export interface EvolutionNode {
  /** Entity id of the work. */
  id: number;
  /** Entity id of the inferred earlier work, or null for roots. */
  parent: number | null;
  /** Similarity score supporting the inferred edge. */
  score: number;
  /** Number of shared tags supporting the edge. */
  shared: number;
  /** Strongest shared tag ids (short list). */
  topTags: number[];
}

export interface EvolutionExport {
  version: number;
  note: string;
  nodes: EvolutionNode[];
}

export interface V2EntityText {
  kind: "label" | "alias" | "description";
  language: string | null;
  value: string;
  primary: boolean;
}

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
  texts?: V2EntityText[];
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
  roleLabel?: string;
  characterLabel?: string;
  weight: number;
  polarity: number;
  confidence?: number;
}

export interface V2Concept {
  id: number;
  label: string;
  description?: string;
  category: string;
  namespace?: string;
  value?: string;
  legacyTagId?: number;
  classificationRule?: string;
  confidence?: number;
  reviewRecommended?: number;
}

export interface V2EntityConcept {
  entityId: number;
  conceptId: number;
  weight: number;
  polarity: number;
  confidence: number | null;
}

export interface V2ConceptExport {
  categories: { id: number; code: string; label: string }[];
  concepts: V2Concept[];
  entityConcepts: V2EntityConcept[];
}

export interface V2AgeRating {
  id: number;
  entityId: number;
  systemId: number;
  certificate: string;
  minimumAge?: number;
  editionLabel?: string;
  descriptorsJson?: string;
  ratingDate?: string;
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
  advisories: unknown[];
  ratings: V2AgeRating[];
  restrictions: V2Restriction[];
}

export interface AppData {
  catalog: CatalogItem[];
  catalogById: Map<number, CatalogItem>;
  tags: Tag[];
  tagById: Map<number, Tag>;
  lookup: Lookup;
  evolution: EvolutionExport | null;
  v2: V2Data | null;
}

export function mergeSettings(raw: unknown): Settings {
  const source = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const merged: Settings = {
    recommendation: { ...DEFAULT_SETTINGS.recommendation },
    evolution: { ...DEFAULT_SETTINGS.evolution },
    islands: { ...DEFAULT_SETTINGS.islands },
  };
  for (const key of ["recommendation", "evolution", "islands"] as const) {
    const section = source[key];
    if (!section || typeof section !== "object") continue;
    const target = merged[key] as unknown as Record<string, number>;
    for (const [name, value] of Object.entries(section)) {
      const num = Number(value);
      if (name in target && Number.isFinite(num) && num >= 0) {
        target[name] = num;
      }
    }
  }
  merged.recommendation.limit = Math.max(1, Math.floor(merged.recommendation.limit));
  return merged;
}

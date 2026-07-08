import type { WorkViewModel } from "./domain";
import type { FeatureSettings } from "./types";

/**
 * Shared weighted, polarity-aware feature model. The semantics are documented
 * once in docs/feature-model.md and implemented identically here and in
 * src/art_islands/features.py; shared/fixtures/feature-golden.json keeps the
 * two implementations honest.
 */

export type FeatureSource = "direct-concept" | "contributor" | "organization" | "content-guide";

export interface WeightedFeature {
  key: string;
  label: string;
  value: number;
  source: FeatureSource;
  /** Concept category label, used for explanation phrasing. */
  category?: string;
  sourceEntityId?: number;
  relationType?: string;
}

export interface EdgeFactor {
  id: string;
  label: string;
  contribution: number;
  source: FeatureSource;
  category?: string;
  relationType?: string;
}

export interface FeatureSimilarity {
  similarity: number;
  sharedFeatureCount: number;
  topFactors: EdgeFactor[];
}

export interface FeatureIndex {
  /** Final (IDF-applied) features per work, key-sorted. */
  featuresById: Map<number, WeightedFeature[]>;
  vectors: Map<number, Map<string, number>>;
  norms: Map<number, number>;
  idf: Map<string, number>;
  documentFrequency: Map<string, number>;
  postings: Map<string, number[]>;
  size: number;
}

/** Features this common are scored but never used for candidate generation. */
export const CANDIDATE_FEATURE_DF_CAP = 150;

const ROLE_MULTIPLIER_KEY: Record<string, keyof FeatureSettings> = {
  creator: "creatorMultiplier",
  composer: "creatorMultiplier",
  lyricist: "creatorMultiplier",
  music_artist: "creatorMultiplier",
  director: "directorMultiplier",
  author: "authorMultiplier",
  screenwriter: "authorMultiplier",
  producer: "producerMultiplier",
  cast_member: "performerMultiplier",
  voice_actor: "performerMultiplier",
  performer: "performerMultiplier",
  production_company: "organizationMultiplier",
  record_label: "organizationMultiplier",
  distributor: "organizationMultiplier",
  publisher: "organizationMultiplier",
  broadcaster: "organizationMultiplier",
};

function magnitude(weight: number): number {
  return Math.max(0, Math.min(1, weight / 100));
}

function polaritySign(polarity: number): 1 | -1 {
  return polarity < 0 ? -1 : 1;
}

export function extractWorkFeatures(work: WorkViewModel, settings: FeatureSettings): WeightedFeature[] {
  const byKey = new Map<string, WeightedFeature>();
  for (const concept of work.concepts) {
    const value = magnitude(concept.weight) * polaritySign(concept.polarity) * settings.directConceptMultiplier;
    if (value === 0) continue;
    const key = `concept:${concept.conceptId}`;
    byKey.set(key, { key, label: concept.label, value, source: "direct-concept", category: concept.categoryLabel });
  }
  for (const contributor of work.contributors) {
    const multiplierKey = ROLE_MULTIPLIER_KEY[contributor.role];
    if (!multiplierKey) continue;
    const value = magnitude(contributor.weight) * polaritySign(contributor.polarity) * settings[multiplierKey];
    if (value === 0) continue;
    const key = `entity:${contributor.entityId}`;
    const existing = byKey.get(key);
    if (existing && Math.abs(existing.value) >= Math.abs(value)) continue;
    byKey.set(key, {
      key,
      label: contributor.label,
      value,
      source:
        contributor.family === "organization" || contributor.family === "group" ? "organization" : "contributor",
      sourceEntityId: contributor.entityId,
      relationType: contributor.role,
    });
  }
  for (const advisory of work.advisories) {
    if (advisory.intensity === undefined || advisory.intensity === null) continue;
    const value = magnitude(advisory.intensity) * settings.contentGuideMultiplier;
    if (value === 0) continue;
    const key = `advisory:${advisory.categoryId}`;
    byKey.set(key, { key, label: advisory.category, value, source: "content-guide" });
  }
  return [...byKey.values()].sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
}

export function buildFeatureIndex(works: WorkViewModel[], settings: FeatureSettings): FeatureIndex {
  const baseById = new Map<number, WeightedFeature[]>();
  const documentFrequency = new Map<string, number>();
  for (const work of works) {
    const features = extractWorkFeatures(work, settings);
    baseById.set(work.id, features);
    for (const feature of features) {
      documentFrequency.set(feature.key, (documentFrequency.get(feature.key) || 0) + 1);
    }
  }
  const total = Math.max(1, works.length);
  const idf = new Map<string, number>();
  for (const [key, df] of documentFrequency) idf.set(key, Math.log(1 + total / df));

  const featuresById = new Map<number, WeightedFeature[]>();
  const vectors = new Map<number, Map<string, number>>();
  const norms = new Map<number, number>();
  const postings = new Map<string, number[]>();
  for (const work of works) {
    const finals: WeightedFeature[] = [];
    const vector = new Map<string, number>();
    let squared = 0;
    for (const feature of baseById.get(work.id) || []) {
      const value = feature.value * (idf.get(feature.key) || 0);
      if (value === 0) continue;
      finals.push({ ...feature, value });
      vector.set(feature.key, value);
      squared += value * value;
      let list = postings.get(feature.key);
      if (!list) postings.set(feature.key, (list = []));
      list.push(work.id);
    }
    featuresById.set(work.id, finals);
    vectors.set(work.id, vector);
    norms.set(work.id, Math.sqrt(squared));
  }
  return { featuresById, vectors, norms, idf, documentFrequency, postings, size: works.length };
}

export function similarityBetween(
  index: FeatureIndex,
  aId: number,
  bId: number,
  topCount = 3,
): FeatureSimilarity {
  const a = index.vectors.get(aId);
  const b = index.vectors.get(bId);
  const normA = index.norms.get(aId) || 0;
  const normB = index.norms.get(bId) || 0;
  if (!a || !b || normA === 0 || normB === 0) {
    return { similarity: 0, sharedFeatureCount: 0, topFactors: [] };
  }
  const [small, large] = a.size <= b.size ? [a, b] : [b, a];
  let dot = 0;
  const shared: { key: string; contribution: number }[] = [];
  for (const [key, value] of small) {
    const other = large.get(key);
    if (other === undefined) continue;
    const contribution = value * other;
    dot += contribution;
    shared.push({ key, contribution });
  }
  shared.sort((x, y) => y.contribution - x.contribution || (x.key < y.key ? -1 : 1));
  const meta = new Map((index.featuresById.get(aId) || []).map((feature) => [feature.key, feature]));
  const topFactors: EdgeFactor[] = shared.slice(0, topCount).map(({ key, contribution }) => {
    const feature = meta.get(key);
    return {
      id: key,
      label: feature?.label ?? key,
      contribution,
      source: feature?.source ?? "direct-concept",
      category: feature?.category,
      relationType: feature?.relationType,
    };
  });
  return { similarity: dot / (normA * normB), sharedFeatureCount: shared.length, topFactors };
}

export function similarityCandidates(
  index: FeatureIndex,
  entityId: number,
  allowed?: Set<number>,
): Set<number> {
  const candidates = new Set<number>();
  const vector = index.vectors.get(entityId);
  if (!vector) return candidates;
  for (const key of vector.keys()) {
    if ((index.documentFrequency.get(key) || 0) > CANDIDATE_FEATURE_DF_CAP) continue;
    for (const otherId of index.postings.get(key) || []) {
      if (otherId === entityId) continue;
      if (allowed && !allowed.has(otherId)) continue;
      candidates.add(otherId);
    }
  }
  return candidates;
}

function roleName(role?: string): string {
  return role ? role.replace(/_/g, " ") : "contributor";
}

/** Human-readable phrase for one evidence factor. */
export function factorPhrase(factor: {
  source: FeatureSource;
  label: string;
  category?: string;
  relationType?: string;
}): string {
  if (factor.source === "direct-concept") {
    return `Shared ${factor.category ? factor.category.toLowerCase() : "concept"}: ${factor.label}`;
  }
  if (factor.source === "content-guide") return `Similar content advisory: ${factor.label}`;
  if (factor.source === "organization") return `Shared ${roleName(factor.relationType)}: ${factor.label}`;
  return `Same ${roleName(factor.relationType)}: ${factor.label}`;
}

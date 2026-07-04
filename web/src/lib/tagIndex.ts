import type { CatalogItem } from "./types";

/**
 * Reusable IDF-weighted tag index over catalog works.
 *
 * Built once per catalog. Extremely common tags get a low inverse document
 * frequency so that generic tags do not dominate similarity, and the
 * tag-to-entity postings lists give bounded candidate generation without
 * comparing every work against every other work.
 */
export interface TagIndex {
  /** entityId -> (tagId -> idf-weighted tag value) */
  vectors: Map<number, Map<number, number>>;
  /** entityId -> Euclidean norm of its vector */
  norms: Map<number, number>;
  /** tagId -> inverse document frequency weight */
  idf: Map<number, number>;
  /** tagId -> entity ids carrying the tag (ascending) */
  entitiesByTag: Map<number, number[]>;
  /** total number of indexed works */
  size: number;
}

export interface SharedTagContribution {
  tagId: number;
  contribution: number;
}

export interface SimilarityResult {
  similarity: number;
  sharedTagCount: number;
  topTags: number[];
}

export function buildTagIndex(catalog: CatalogItem[]): TagIndex {
  const documentFrequency = new Map<number, number>();
  for (const item of catalog) {
    for (const [tagId] of item.tags || []) {
      documentFrequency.set(tagId, (documentFrequency.get(tagId) || 0) + 1);
    }
  }

  const total = Math.max(1, catalog.length);
  const idf = new Map<number, number>();
  for (const [tagId, df] of documentFrequency) {
    idf.set(tagId, Math.log(1 + total / df));
  }

  const vectors = new Map<number, Map<number, number>>();
  const norms = new Map<number, number>();
  const entitiesByTag = new Map<number, number[]>();

  for (const item of catalog) {
    const vector = new Map<number, number>();
    let squared = 0;
    for (const [tagId, weight] of item.tags || []) {
      const normalizedWeight = Math.max(0, Math.min(1, weight / 100));
      const value = normalizedWeight * (idf.get(tagId) || 0);
      if (value <= 0) continue;
      vector.set(tagId, value);
      squared += value * value;
      let postings = entitiesByTag.get(tagId);
      if (!postings) {
        postings = [];
        entitiesByTag.set(tagId, postings);
      }
      postings.push(item.id);
    }
    vectors.set(item.id, vector);
    norms.set(item.id, Math.sqrt(squared));
  }

  return { vectors, norms, idf, entitiesByTag, size: catalog.length };
}

/** Cosine similarity plus an explanation of the strongest shared tags. */
export function similarityBetween(
  index: TagIndex,
  aId: number,
  bId: number,
  topTagCount = 3,
): SimilarityResult {
  const a = index.vectors.get(aId);
  const b = index.vectors.get(bId);
  const normA = index.norms.get(aId) || 0;
  const normB = index.norms.get(bId) || 0;
  if (!a || !b || normA === 0 || normB === 0) {
    return { similarity: 0, sharedTagCount: 0, topTags: [] };
  }

  const [small, large] = a.size <= b.size ? [a, b] : [b, a];
  let dot = 0;
  const shared: SharedTagContribution[] = [];
  for (const [tagId, value] of small) {
    const other = large.get(tagId);
    if (other === undefined) continue;
    const contribution = value * other;
    dot += contribution;
    shared.push({ tagId, contribution });
  }

  shared.sort((x, y) => y.contribution - x.contribution || x.tagId - y.tagId);
  return {
    similarity: dot / (normA * normB),
    sharedTagCount: shared.length,
    topTags: shared.slice(0, topTagCount).map((entry) => entry.tagId),
  };
}

/**
 * Candidate ids sharing at least one tag with the given entity, generated
 * from the postings lists and restricted to an allowed set when provided.
 */
export function coTaggedCandidates(
  index: TagIndex,
  entityId: number,
  allowed?: Set<number>,
): Set<number> {
  const vector = index.vectors.get(entityId);
  const candidates = new Set<number>();
  if (!vector) return candidates;
  for (const tagId of vector.keys()) {
    const postings = index.entitiesByTag.get(tagId);
    if (!postings) continue;
    for (const otherId of postings) {
      if (otherId === entityId) continue;
      if (allowed && !allowed.has(otherId)) continue;
      candidates.add(otherId);
    }
  }
  return candidates;
}

/** Broad work kind used for grouping and lineage preferences. */
export function broadKind(kind: number): "film" | "music" | "game" | "work" {
  if (kind === 1) return "film";
  if (kind === 2) return "music";
  if (kind === 6) return "game";
  return "work";
}

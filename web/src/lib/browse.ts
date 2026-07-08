import type { DomainModel, WorkViewModel } from "./domain";
import type { FeatureIndex } from "./features";

export interface Filters {
  q: string;
  minDate: string;
  maxDate: string;
  type: string;
  conceptId: string;
}

export const EMPTY_FILTERS: Filters = { q: "", minDate: "", maxDate: "", type: "", conceptId: "" };

export function hasRelevanceContext(filters: Filters): boolean {
  return Boolean(filters.q.trim() || filters.conceptId);
}

export function filterWorks(domain: DomainModel, filters: Filters): WorkViewModel[] {
  const q = filters.q.trim().toLowerCase();
  return domain.works.filter((work) => {
    if (filters.type && work.type !== filters.type) return false;
    if (filters.minDate && (!work.sortDate || work.sortDate < filters.minDate)) return false;
    if (filters.maxDate && (!work.sortDate || work.sortDate > filters.maxDate)) return false;
    if (filters.conceptId && !work.concepts.some((concept) => String(concept.conceptId) === filters.conceptId)) {
      return false;
    }
    if (!q) return true;
    return (
      work.label.toLowerCase().includes(q) ||
      work.concepts.some((concept) => concept.label.toLowerCase().includes(q)) ||
      work.contributors.some((contributor) => contributor.label.toLowerCase().includes(q))
    );
  });
}

/**
 * Relevance scores for the current query/concept context, using the shared
 * feature semantics: positive high-weight matches rank first, explicit
 * negative associations sink below positive ones. Returns null when there is
 * no query or concept filter — literal sorts are never affected.
 */
export function relevanceScores(
  index: FeatureIndex,
  works: WorkViewModel[],
  filters: Filters,
): Map<number, number> | null {
  const q = filters.q.trim().toLowerCase();
  if (!q && !filters.conceptId) return null;
  const scores = new Map<number, number>();
  for (const work of works) {
    let score = 0;
    if (filters.conceptId) {
      score += index.vectors.get(work.id)?.get(`concept:${filters.conceptId}`) ?? 0;
    }
    if (q) {
      for (const feature of index.featuresById.get(work.id) || []) {
        if (feature.label.toLowerCase().includes(q)) score += feature.value;
      }
      if (work.label.toLowerCase().includes(q)) score += 2;
    }
    scores.set(work.id, score);
  }
  return scores;
}

/**
 * Date, Label, and Kind stay literal deterministic sorts; "relevance" uses
 * the feature-based scores and falls back to the date order for ties.
 */
export function sortWorks(
  works: WorkViewModel[],
  sortMode: string,
  relevance: Map<number, number> | null,
): WorkViewModel[] {
  const copy = [...works];
  const byDate = (a: WorkViewModel, b: WorkViewModel) =>
    (a.sortDate || "9999-99-99").localeCompare(b.sortDate || "9999-99-99") ||
    a.label.localeCompare(b.label) ||
    a.id - b.id;
  if (sortMode === "relevance" && relevance) {
    return copy.sort((a, b) => (relevance.get(b.id) || 0) - (relevance.get(a.id) || 0) || byDate(a, b));
  }
  if (sortMode === "label") {
    return copy.sort((a, b) => a.label.localeCompare(b.label) || a.id - b.id);
  }
  if (sortMode === "kind") {
    return copy.sort(
      (a, b) => a.typeLabel.localeCompare(b.typeLabel) || a.label.localeCompare(b.label) || a.id - b.id,
    );
  }
  return copy.sort(byDate);
}

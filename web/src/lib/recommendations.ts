import type { CatalogItem, Ratings, RecommendationSettings, Settings } from "./types";
import { DEFAULT_SETTINGS } from "./types";

export interface ScoredRecommendation {
  item: CatalogItem;
  score: number;
  likedSharedTags: number;
  dislikedSharedTags: number;
}

function finiteNumber(value: unknown, fallback: number): number {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : fallback;
}

export function recommendationSettings(settings?: Partial<Settings> | null): RecommendationSettings {
  const source: Partial<RecommendationSettings> = settings?.recommendation ?? {};
  const defaults = DEFAULT_SETTINGS.recommendation;
  return {
    likeWeight: finiteNumber(source.likeWeight, defaults.likeWeight),
    dislikeWeight: finiteNumber(source.dislikeWeight, defaults.dislikeWeight),
    limit: Math.max(1, Math.floor(finiteNumber(source.limit, defaults.limit))),
  };
}

export function normalizedTagMap(item: CatalogItem): Map<string, number> {
  const result = new Map<string, number>();
  for (const row of item.tags || []) {
    const tagId = String(row[0]);
    const rawWeight = Number(row[1]);
    const weight = Number.isFinite(rawWeight) ? rawWeight : 50;
    result.set(tagId, Math.max(0, Math.min(1, weight / 100)));
  }
  return result;
}

function addEvidence(target: Map<string, number>, item: CatalogItem): void {
  for (const [tagId, weight] of normalizedTagMap(item)) {
    target.set(tagId, (target.get(tagId) || 0) + weight);
  }
}

function compareByDateAndLabel(a: ScoredRecommendation, b: ScoredRecommendation): number {
  const dateA = a.item.date || "9999-99-99";
  const dateB = b.item.date || "9999-99-99";
  if (dateA !== dateB) return dateA.localeCompare(dateB);
  return String(a.item.label || "").localeCompare(String(b.item.label || ""));
}

/**
 * Tag-overlap recommendation scoring. Behavior preserved from the previous
 * static frontend: liked tags add evidence, disliked tags subtract, scores
 * are normalized by tag-list size, and candidates need positive liked
 * evidence and a positive final score.
 */
export function scoreRecommendations(
  catalog: CatalogItem[],
  ratings: Ratings,
  settings?: Partial<Settings> | null,
): ScoredRecommendation[] {
  const config = recommendationSettings(settings);
  const liked = new Map<string, number>();
  const disliked = new Map<string, number>();
  let likedCount = 0;

  for (const item of catalog || []) {
    const rating = ratings[String(item.id)];
    if (rating === 1) {
      likedCount += 1;
      addEvidence(liked, item);
    } else if (rating === -1) {
      addEvidence(disliked, item);
    }
  }

  if (likedCount === 0) return [];

  const scored: ScoredRecommendation[] = [];
  for (const item of catalog || []) {
    const rating = ratings[String(item.id)];
    if (rating === 1 || rating === -1) continue;

    const candidateTags = normalizedTagMap(item);
    let likedShared = 0;
    let dislikedShared = 0;
    let score = 0;

    for (const [tagId, candidateWeight] of candidateTags) {
      const likedEvidence = liked.get(tagId);
      if (likedEvidence !== undefined) {
        likedShared += 1;
        score += config.likeWeight * candidateWeight * likedEvidence;
      }
      const dislikedEvidence = disliked.get(tagId);
      if (dislikedEvidence !== undefined) {
        dislikedShared += 1;
        score -= config.dislikeWeight * candidateWeight * dislikedEvidence;
      }
    }

    if (likedShared === 0) continue;

    const volumeNormalization = Math.pow(Math.max(1, candidateTags.size), 0.35);
    score = score / volumeNormalization;
    if (score <= 0) continue;

    scored.push({
      item,
      score,
      likedSharedTags: likedShared,
      dislikedSharedTags: dislikedShared,
    });
  }

  return scored
    .sort((a, b) => b.score - a.score || compareByDateAndLabel(a, b))
    .slice(0, config.limit);
}

export function explanation(result: ScoredRecommendation): string {
  const parts: string[] = [];
  if (result.likedSharedTags) {
    parts.push(`${result.likedSharedTags} shared liked tag${result.likedSharedTags === 1 ? "" : "s"}`);
  }
  if (result.dislikedSharedTags) {
    parts.push(`${result.dislikedSharedTags} shared disliked tag${result.dislikedSharedTags === 1 ? "" : "s"}`);
  }
  return parts.join(", ");
}

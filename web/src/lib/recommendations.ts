import type { DomainModel, WorkViewModel } from "./domain";
import type { EdgeFactor, FeatureIndex } from "./features";
import { factorPhrase } from "./features";
import type { Ratings, Settings } from "./types";

/** One signed score contribution, with provenance for explanations. */
export type ScoreContribution = EdgeFactor;

export interface ScoredRecommendation {
  work: WorkViewModel;
  score: number;
  /** Positive evidence, strongest first (all entries kept; UI slices). */
  positive: ScoreContribution[];
  /** Negative evidence, strongest first by |contribution|. */
  negative: ScoreContribution[];
}

/**
 * Feature-based recommendation scoring. Liked works add their weighted,
 * polarity-aware, IDF-scaled feature vectors to a preference profile;
 * disliked works subtract (scaled by dislikeWeight). Candidates need at
 * least one positive contribution and a positive volume-normalized score.
 * Contributions retain provenance so the UI can explain both directions.
 */
export function scoreRecommendations(
  domain: DomainModel,
  index: FeatureIndex,
  ratings: Ratings,
  settings: Settings,
): ScoredRecommendation[] {
  const config = settings.recommendation;
  const profile = new Map<string, number>();
  let likedCount = 0;

  for (const work of domain.works) {
    const rating = ratings[String(work.id)];
    if (rating !== 1 && rating !== -1) continue;
    const direction = rating === 1 ? config.likeWeight : -config.dislikeWeight;
    if (rating === 1) likedCount += 1;
    for (const [key, value] of index.vectors.get(work.id) || []) {
      profile.set(key, (profile.get(key) || 0) + direction * value);
    }
  }
  if (!likedCount) return [];

  const scored: ScoredRecommendation[] = [];
  for (const work of domain.works) {
    const rating = ratings[String(work.id)];
    if (rating === 1 || rating === -1) continue;
    const vector = index.vectors.get(work.id);
    if (!vector || vector.size === 0) continue;

    const meta = new Map((index.featuresById.get(work.id) || []).map((feature) => [feature.key, feature]));
    let score = 0;
    const positive: ScoreContribution[] = [];
    const negative: ScoreContribution[] = [];
    for (const [key, value] of vector) {
      const evidence = profile.get(key);
      if (evidence === undefined) continue;
      const amount = value * evidence;
      if (amount === 0) continue;
      score += amount;
      const feature = meta.get(key)!;
      const entry: ScoreContribution = {
        id: key,
        label: feature.label,
        contribution: amount,
        source: feature.source,
        category: feature.category,
        relationType: feature.relationType,
      };
      (amount > 0 ? positive : negative).push(entry);
    }
    if (!positive.length) continue;

    score /= Math.pow(Math.max(1, vector.size), 0.35);
    if (score <= 0) continue;

    positive.sort((a, b) => b.contribution - a.contribution || (a.id < b.id ? -1 : 1));
    negative.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution) || (a.id < b.id ? -1 : 1));
    scored.push({ work, score, positive, negative });
  }

  return scored
    .sort(
      (a, b) =>
        b.score - a.score ||
        (a.work.sortDate || "9999-99-99").localeCompare(b.work.sortDate || "9999-99-99") ||
        a.work.label.localeCompare(b.work.label) ||
        a.work.id - b.work.id,
    )
    .slice(0, config.limit);
}

/** Compact one-line explanation for a recommendation. */
export function explanationText(result: ScoredRecommendation, topCount = 3): string {
  const parts = result.positive.slice(0, topCount).map(factorPhrase);
  if (result.negative.length) parts.push(`offset by: ${factorPhrase(result.negative[0])}`);
  return parts.join(" · ");
}

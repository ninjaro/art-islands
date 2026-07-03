(function initRecommendations(root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.ArtIslandsRecommendations = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function recommendationFactory() {
  const DEFAULTS = {
    recommendation: {
      likeWeight: 1.0,
      dislikeWeight: 1.5,
      limit: 100,
    },
  };

  function recommendationSettings(settings) {
    const source = settings && settings.recommendation ? settings.recommendation : {};
    const likeWeight = finiteNumber(source.likeWeight, DEFAULTS.recommendation.likeWeight);
    const dislikeWeight = finiteNumber(source.dislikeWeight, DEFAULTS.recommendation.dislikeWeight);
    const limit = Math.max(1, Math.floor(finiteNumber(source.limit, DEFAULTS.recommendation.limit)));
    return { likeWeight, dislikeWeight, limit };
  }

  function finiteNumber(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) && number >= 0 ? number : fallback;
  }

  function normalizedTagMap(item) {
    const result = new Map();
    for (const row of item.tags || []) {
      const tagId = String(row[0]);
      const rawWeight = Number(row[1]);
      const weight = Number.isFinite(rawWeight) ? rawWeight : 50;
      result.set(tagId, Math.max(0, Math.min(1, weight / 100)));
    }
    return result;
  }

  function addEvidence(target, item) {
    for (const [tagId, weight] of normalizedTagMap(item)) {
      target.set(tagId, (target.get(tagId) || 0) + weight);
    }
  }

  function compareByDateAndLabel(a, b) {
    const dateA = a.item.date || "9999-99-99";
    const dateB = b.item.date || "9999-99-99";
    if (dateA !== dateB) return dateA.localeCompare(dateB);
    return String(a.item.label || "").localeCompare(String(b.item.label || ""));
  }

  function scoreRecommendations(catalog, ratings, settings) {
    const config = recommendationSettings(settings);
    const liked = new Map();
    const disliked = new Map();
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

    const scored = [];
    for (const item of catalog || []) {
      if (ratings[String(item.id)] === 1 || ratings[String(item.id)] === -1) {
        continue;
      }

      const candidateTags = normalizedTagMap(item);
      const likedShared = new Set();
      const dislikedShared = new Set();
      let score = 0;

      for (const [tagId, candidateWeight] of candidateTags) {
        if (liked.has(tagId)) {
          likedShared.add(tagId);
          score += config.likeWeight * candidateWeight * liked.get(tagId);
        }
        if (disliked.has(tagId)) {
          dislikedShared.add(tagId);
          score -= config.dislikeWeight * candidateWeight * disliked.get(tagId);
        }
      }

      if (likedShared.size === 0) continue;

      const volumeNormalization = Math.pow(Math.max(1, candidateTags.size), 0.35);
      score = score / volumeNormalization;
      if (score <= 0) continue;

      scored.push({
        item,
        score,
        likedSharedTags: likedShared.size,
        dislikedSharedTags: dislikedShared.size,
      });
    }

    return scored
      .sort((a, b) => b.score - a.score || compareByDateAndLabel(a, b))
      .slice(0, config.limit);
  }

  function explanation(result) {
    const parts = [];
    if (result.likedSharedTags) {
      parts.push(`${result.likedSharedTags} shared liked tag${result.likedSharedTags === 1 ? "" : "s"}`);
    }
    if (result.dislikedSharedTags) {
      parts.push(`${result.dislikedSharedTags} shared disliked tag${result.dislikedSharedTags === 1 ? "" : "s"}`);
    }
    return parts.join(", ");
  }

  return {
    DEFAULTS,
    explanation,
    recommendationSettings,
    scoreRecommendations,
  };
});

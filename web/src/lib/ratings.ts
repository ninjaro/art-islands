import type { Ratings, RatingValue } from "./types";

/** localStorage format shared with the previous static app. Do not change. */
export const RATINGS_KEY = "art-islands-ratings-v1";

export function loadRatings(storage: Pick<Storage, "getItem"> = localStorage): Ratings {
  try {
    const raw: unknown = JSON.parse(storage.getItem(RATINGS_KEY) || "{}");
    const ratings: Ratings = {};
    if (raw && typeof raw === "object") {
      for (const [id, value] of Object.entries(raw)) {
        if (value === 1 || value === -1) ratings[id] = value;
      }
    }
    return ratings;
  } catch {
    return {};
  }
}

export function saveRatings(
  ratings: Ratings,
  storage: Pick<Storage, "setItem"> = localStorage,
): void {
  storage.setItem(RATINGS_KEY, JSON.stringify(ratings));
}

/** Toggle semantics: rating the same value again removes the rating. */
export function toggleRating(ratings: Ratings, id: number, value: RatingValue): Ratings {
  const key = String(id);
  const next = { ...ratings };
  if (next[key] === value) {
    delete next[key];
  } else {
    next[key] = value;
  }
  return next;
}

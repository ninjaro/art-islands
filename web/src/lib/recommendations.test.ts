import { describe, expect, test } from "vitest";
import { explanation, scoreRecommendations } from "./recommendations";
import type { CatalogItem, TagEntry } from "./types";

function work(id: number, label: string, date: string | null, tags: TagEntry[]): CatalogItem {
  return { id, label, kind: 1, date, datePrecision: 3, image: null, refs: [], tags, links: [] };
}

describe("scoreRecommendations", () => {
  test("scores unrated catalog items from liked tag overlap", () => {
    const catalog = [
      work(1, "Liked", "1980-01-01", [[10, 100, 0], [20, 25, 0]]),
      work(2, "Disliked", "1970-01-01", [[30, 100, 0], [10, 50, 0]]),
      work(3, "Best candidate", "1960-01-01", [[10, 100, 0], [40, 50, 0]]),
      work(4, "Mixed candidate", "1950-01-01", [[10, 100, 0], [30, 20, 0]]),
      work(5, "No evidence", "1940-01-01", [[99, 100, 0]]),
    ];

    const results = scoreRecommendations(
      catalog,
      { "1": 1, "2": -1 },
      {
        recommendation: { likeWeight: 2, dislikeWeight: 1, limit: 10 },
      },
    );

    expect(results.map((result) => result.item.id)).toEqual([3, 4]);
    expect(results[0].likedSharedTags).toBe(1);
    expect(results[0].dislikedSharedTags).toBe(1);
    expect(explanation(results[0])).toBe("1 shared liked tag, 1 shared disliked tag");
  });

  test("returns no recommendations without liked records", () => {
    const results = scoreRecommendations(
      [work(1, "Only", "2000-01-01", [[10, 100, 0]])],
      { "1": -1 },
      null,
    );
    expect(results).toEqual([]);
  });

  test("applies configured recommendation limit", () => {
    const catalog = [
      work(1, "Liked", "2000-01-01", [[10, 100, 0]]),
      work(2, "A", "1990-01-01", [[10, 100, 0]]),
      work(3, "B", "1991-01-01", [[10, 100, 0]]),
    ];

    const results = scoreRecommendations(
      catalog,
      { "1": 1 },
      { recommendation: { likeWeight: 1, dislikeWeight: 1, limit: 1 } },
    );

    expect(results).toHaveLength(1);
    expect(results[0].item.id).toBe(2);
  });

  test("rated works never appear as recommendations", () => {
    const catalog = [
      work(1, "Liked", "2000-01-01", [[10, 100, 0]]),
      work(2, "Disliked", "1990-01-01", [[20, 100, 0]]),
      work(3, "Fresh", "1991-01-01", [[10, 100, 0]]),
    ];
    const results = scoreRecommendations(catalog, { "1": 1, "2": -1 }, null);
    expect(results.map((result) => result.item.id)).toEqual([3]);
  });

  test("dislike overlap lowers the score", () => {
    const catalog = [
      work(1, "Liked", "2000-01-01", [[10, 100, 0]]),
      work(2, "Disliked", "1999-01-01", [[20, 100, 0]]),
      work(3, "Pure", "1991-01-01", [[10, 100, 0]]),
      work(4, "Tainted", "1992-01-01", [[10, 100, 0], [20, 100, 0]]),
    ];
    const results = scoreRecommendations(catalog, { "1": 1, "2": -1 }, {
      recommendation: { likeWeight: 1, dislikeWeight: 0.5, limit: 10 },
    });
    const pure = results.find((result) => result.item.id === 3);
    const tainted = results.find((result) => result.item.id === 4);
    expect(pure).toBeDefined();
    expect(tainted).toBeDefined();
    expect(tainted!.score).toBeLessThan(pure!.score);
  });
});

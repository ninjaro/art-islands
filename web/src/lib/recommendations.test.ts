import { describe, expect, it } from "vitest";
import { buildFeatureIndex } from "./features";
import { explanationText, scoreRecommendations } from "./recommendations";
import { makeDomain, makeWork } from "./testFixtures";
import { DEFAULT_SETTINGS } from "./types";
import type { Ratings } from "./types";

function setup(specs: Parameters<typeof makeWork>[1][]) {
  const works = specs.map((spec, index) => makeWork(index + 1, spec));
  const domain = makeDomain(works);
  const index = buildFeatureIndex(works, DEFAULT_SETTINGS.features);
  return { domain, index };
}

function score(specs: Parameters<typeof makeWork>[1][], ratings: Ratings) {
  const { domain, index } = setup(specs);
  return scoreRecommendations(domain, index, ratings, DEFAULT_SETTINGS);
}

describe("scoreRecommendations", () => {
  it("returns empty without likes", () => {
    expect(score([{ concepts: [{ id: 1, weight: 80 }] }, { concepts: [{ id: 1, weight: 80 }] }], {})).toEqual([]);
    expect(
      score([{ concepts: [{ id: 1, weight: 80 }] }, { concepts: [{ id: 1, weight: 80 }] }], { "1": -1 }),
    ).toEqual([]);
  });

  it("excludes already rated works", () => {
    const results = score(
      [
        { concepts: [{ id: 1, weight: 80 }] },
        { concepts: [{ id: 2, weight: 80 }] },
        { concepts: [{ id: 1, weight: 80 }] },
      ],
      { "1": 1, "2": -1 },
    );
    expect(results.map((entry) => entry.work.id)).toEqual([3]);
  });

  it("requires positive evidence", () => {
    const results = score(
      [
        { concepts: [{ id: 1, weight: 80 }] }, // liked
        { concepts: [{ id: 2, weight: 80 }] }, // disliked
        { concepts: [{ id: 2, weight: 60 }] }, // shares only disliked features
      ],
      { "1": 1, "2": -1 },
    );
    expect(results).toEqual([]);
  });

  it("disliked evidence subtracts", () => {
    const specs = [
      { concepts: [{ id: 1, weight: 80 }] },
      { concepts: [{ id: 2, weight: 80 }] },
      { concepts: [{ id: 1, weight: 70 }, { id: 2, weight: 20 }, { id: 3, weight: 10 }] },
    ];
    const [withoutDislike] = score(specs, { "1": 1 });
    const [withDislike] = score(specs, { "1": 1, "2": -1 });
    expect(withDislike.score).toBeLessThan(withoutDislike.score);
    expect(withDislike.negative.length).toBeGreaterThan(0);
  });

  it("candidate weight matters and negative polarity is not positive evidence", () => {
    const results = score(
      [
        { concepts: [{ id: 1, weight: 90 }, { id: 9, weight: 10 }] }, // liked
        { concepts: [{ id: 1, weight: 90 }, { id: 8, weight: 10 }] }, // strong match
        { concepts: [{ id: 1, weight: 30 }, { id: 7, weight: 10 }] }, // weak match
        { concepts: [{ id: 1, weight: 90, polarity: -1 }, { id: 6, weight: 10 }] }, // anti-match
      ],
      { "1": 1 },
    );
    const ids = results.map((entry) => entry.work.id);
    expect(ids[0]).toBe(2);
    expect(ids.indexOf(2)).toBeLessThan(ids.indexOf(3));
    expect(ids).not.toContain(4); // negative polarity match is negative evidence, not positive
  });

  it("inherited contributor evidence is weaker than direct concepts", () => {
    const viaConcept = score(
      [
        { concepts: [{ id: 1, weight: 80 }, { id: 5, weight: 40 }] },
        { concepts: [{ id: 1, weight: 80 }, { id: 6, weight: 40 }] },
      ],
      { "1": 1 },
    )[0];
    const viaDirector = score(
      [
        { concepts: [{ id: 5, weight: 40 }], contributors: [{ entityId: 50, role: "director", weight: 80 }] },
        { concepts: [{ id: 6, weight: 40 }], contributors: [{ entityId: 50, role: "director", weight: 80 }] },
      ],
      { "1": 1 },
    )[0];
    expect(viaDirector.score).toBeLessThan(viaConcept.score);
    expect(viaDirector.positive[0].source).toBe("contributor");
  });

  it("keeps positive and negative contributions for explanation", () => {
    const [top] = score(
      [
        { concepts: [{ id: 1, label: "Thriller", category: "Genre", weight: 80 }] },
        { concepts: [{ id: 2, label: "Slapstick", category: "Genre", weight: 80 }] },
        {
          concepts: [
            { id: 1, label: "Thriller", category: "Genre", weight: 70 },
            { id: 2, label: "Slapstick", category: "Genre", weight: 30 },
            { id: 3, weight: 10 },
          ],
        },
      ],
      { "1": 1, "2": -1 },
    );
    expect(top.positive[0].label).toBe("Thriller");
    expect(top.negative[0].label).toBe("Slapstick");
    const text = explanationText(top);
    expect(text).toContain("Shared genre: Thriller");
    expect(text).toContain("offset by: Shared genre: Slapstick");
  });

  it("is deterministic and respects the limit", () => {
    const specs = [...Array(30).keys()].map((index) => ({
      concepts: [
        { id: 1, weight: 80 },
        { id: 100 + index, weight: 50 },
      ],
    }));
    const settings = { ...DEFAULT_SETTINGS, recommendation: { ...DEFAULT_SETTINGS.recommendation, limit: 5 } };
    const { domain, index } = setup(specs);
    const first = scoreRecommendations(domain, index, { "1": 1 }, settings);
    const second = scoreRecommendations(domain, index, { "1": 1 }, settings);
    expect(first).toHaveLength(5);
    expect(first.map((entry) => entry.work.id)).toEqual(second.map((entry) => entry.work.id));
  });
});

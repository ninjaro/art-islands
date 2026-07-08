import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { WorkViewModel } from "./domain";
import { buildFeatureIndex, similarityBetween } from "./features";
import type { FeatureSettings } from "./types";

interface GoldenWork {
  id: number;
  date: string | null;
  kind: string;
  concepts: Array<{ id: number; label: string; category: string; weight: number; polarity: number }>;
  contributors: Array<{
    entityId: number;
    label: string;
    family: string;
    role: string;
    weight: number;
    polarity: number;
  }>;
  advisories: Array<{ categoryId: number; label: string; intensity: number | null }>;
}

interface Golden {
  settings: FeatureSettings;
  works: GoldenWork[];
  expected: {
    features: Record<string, Record<string, number>>;
    similarities: Array<{
      a: number;
      b: number;
      similarity: number;
      sharedFeatureCount: number;
      topFactors: Array<{ id: string; label: string; contribution: number; source: string }>;
    }>;
  };
}

const golden: Golden = JSON.parse(
  readFileSync(new URL("../../../shared/fixtures/feature-golden.json", import.meta.url), "utf-8"),
);

function toWorkViewModel(work: GoldenWork): WorkViewModel {
  return {
    id: work.id,
    label: `Work ${work.id}`,
    family: "work",
    type: work.kind,
    typeLabel: work.kind,
    broadKind: "work",
    dates: [],
    sortDate: work.date,
    year: work.date ? Number(work.date.slice(0, 4)) : null,
    concepts: work.concepts.map((concept) => ({
      conceptId: concept.id,
      label: concept.label,
      category: concept.category.toLowerCase(),
      categoryLabel: concept.category,
      weight: concept.weight,
      polarity: concept.polarity,
    })),
    conceptsByCategory: {},
    contributors: [...work.contributors]
      .sort((a, b) => a.role.localeCompare(b.role))
      .map((contributor) => ({
        entityId: contributor.entityId,
        label: contributor.label,
        role: contributor.role,
        roleLabel: contributor.role,
        family: contributor.family,
        weight: contributor.weight,
        polarity: contributor.polarity,
      })),
    contributorsByRole: {},
    measurements: [],
    ageRatings: [],
    advisories: work.advisories.map((advisory) => ({
      categoryId: advisory.categoryId,
      category: advisory.label,
      intensity: advisory.intensity ?? undefined,
    })),
    restrictions: [],
    identifiers: [],
  };
}

describe("cross-language golden fixtures", () => {
  const index = buildFeatureIndex(golden.works.map(toWorkViewModel), golden.settings);

  it("reproduces every final feature value from the Python reference", () => {
    for (const [workId, expectedFeatures] of Object.entries(golden.expected.features)) {
      const vector = index.vectors.get(Number(workId))!;
      expect(vector.size).toBe(Object.keys(expectedFeatures).length);
      for (const [key, expected] of Object.entries(expectedFeatures)) {
        expect(vector.get(key), `work ${workId} ${key}`).toBeCloseTo(expected, 9);
      }
    }
  });

  it("reproduces every pairwise similarity, shared count, and top factors", () => {
    for (const entry of golden.expected.similarities) {
      const result = similarityBetween(index, entry.a, entry.b);
      expect(result.similarity, `similarity ${entry.a}-${entry.b}`).toBeCloseTo(entry.similarity, 9);
      expect(result.sharedFeatureCount, `shared ${entry.a}-${entry.b}`).toBe(entry.sharedFeatureCount);
      expect(result.topFactors.map((factor) => factor.id)).toEqual(entry.topFactors.map((factor) => factor.id));
      expect(result.topFactors.map((factor) => factor.source)).toEqual(
        entry.topFactors.map((factor) => factor.source),
      );
      result.topFactors.forEach((factor, position) => {
        expect(factor.contribution).toBeCloseTo(entry.topFactors[position].contribution, 9);
      });
    }
  });
});

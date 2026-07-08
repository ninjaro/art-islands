import { describe, expect, it } from "vitest";
import type { WorkViewModel } from "./domain";
import {
  buildFeatureIndex,
  CANDIDATE_FEATURE_DF_CAP,
  extractWorkFeatures,
  factorPhrase,
  similarityBetween,
  similarityCandidates,
} from "./features";
import { DEFAULT_SETTINGS } from "./types";

const settings = DEFAULT_SETTINGS.features;

interface WorkSpec {
  concepts?: Array<{ id: number; label?: string; category?: string; weight: number | null; polarity?: number }>;
  contributors?: Array<{ entityId: number; label?: string; role: string; family?: string; weight: number; polarity?: number }>;
  advisories?: Array<{ categoryCode: string; category?: string; intensity?: number }>;
}

function work(id: number, spec: WorkSpec = {}): WorkViewModel {
  const concepts = (spec.concepts ?? []).map((concept) => ({
    conceptId: concept.id,
    label: concept.label ?? `Concept ${concept.id}`,
    category: "genre",
    categoryLabel: concept.category ?? "Genre",
    weight: concept.weight,
    polarity: concept.polarity ?? 0,
  }));
  const contributors = (spec.contributors ?? []).map((contributor) => ({
    entityId: contributor.entityId,
    label: contributor.label ?? `Entity ${contributor.entityId}`,
    role: contributor.role,
    roleLabel: contributor.role,
    family: contributor.family ?? "person",
    weight: contributor.weight,
    polarity: contributor.polarity ?? 0,
  }));
  const advisories = (spec.advisories ?? []).map((advisory) => ({
    categoryCode: advisory.categoryCode,
    category: advisory.category ?? advisory.categoryCode,
    intensity: advisory.intensity,
  }));
  return {
    id,
    label: `Work ${id}`,
    family: "work",
    type: "film",
    typeLabel: "Film",
    broadKind: "film",
    dates: [],
    sortDate: null,
    year: null,
    concepts,
    conceptsByCategory: {},
    contributors,
    contributorsByRole: {},
    measurements: [],
    advisories,
    restrictions: [],
    identifiers: [],
  };
}

describe("extractWorkFeatures", () => {
  it("contributor features use role multipliers and are weaker than direct concepts", () => {
    const features = extractWorkFeatures(
      work(1, {
        concepts: [{ id: 1, weight: 80 }],
        contributors: [{ entityId: 50, role: "director", weight: 80 }],
      }),
      settings,
    );
    const direct = features.find((f) => f.key === "concept:1")!;
    const director = features.find((f) => f.key === "entity:50")!;
    expect(direct.value).toBeCloseTo(0.8, 10);
    expect(director.value).toBeCloseTo(0.8 * 0.5, 10);
    expect(director.source).toBe("contributor");
    expect(director.relationType).toBe("director");
  });

  it("keeps only the strongest role for a repeated entity", () => {
    const features = extractWorkFeatures(
      work(1, {
        contributors: [
          { entityId: 50, role: "cast_member", weight: 80 },
          { entityId: 50, role: "director", weight: 80 },
        ],
      }),
      settings,
    );
    const entries = features.filter((f) => f.key === "entity:50");
    expect(entries).toHaveLength(1);
    expect(entries[0].relationType).toBe("director");
  });

  it("unmapped roles produce no inherited feature", () => {
    const features = extractWorkFeatures(
      work(1, { contributors: [{ entityId: 50, role: "main_subject", weight: 80 }] }),
      settings,
    );
    expect(features).toHaveLength(0);
  });

  it("organization targets get source organization", () => {
    const features = extractWorkFeatures(
      work(1, { contributors: [{ entityId: 60, role: "production_company", family: "organization", weight: 40 }] }),
      settings,
    );
    expect(features[0].source).toBe("organization");
    expect(features[0].value).toBeCloseTo(0.4 * 0.2, 10);
  });

  it("advisories become content-guide features from intensity", () => {
    const features = extractWorkFeatures(
      work(1, { advisories: [{ categoryCode: "violence", category: "Violence", intensity: 72 }, { categoryCode: "other" }] }),
      settings,
    );
    expect(features).toHaveLength(1);
    expect(features[0]).toMatchObject({ key: "advisory:violence", label: "Violence", source: "content-guide" });
    expect(features[0].value).toBeCloseTo(0.72 * 0.25, 10);
  });

  it("negative polarity flips the sign", () => {
    const [feature] = extractWorkFeatures(work(1, { concepts: [{ id: 1, weight: 60, polarity: -1 }] }), settings);
    expect(feature.value).toBeCloseTo(-0.6, 10);
  });

  it("skips uncalibrated null concept weights", () => {
    const features = extractWorkFeatures(
      work(1, { concepts: [{ id: 1, weight: null }, { id: 2, weight: 60 }] }),
      settings,
    );
    expect(features.map((feature) => feature.key)).toEqual(["concept:2"]);
  });
});

describe("buildFeatureIndex + similarityBetween", () => {
  it("higher weight on a matching feature raises similarity", () => {
    const works = [
      work(1, { concepts: [{ id: 1, weight: 90 }, { id: 2, weight: 50 }] }),
      work(2, { concepts: [{ id: 1, weight: 90 }, { id: 3, weight: 50 }] }),
      work(3, { concepts: [{ id: 1, weight: 30 }, { id: 3, weight: 50 }] }),
    ];
    const index = buildFeatureIndex(works, settings);
    const strong = similarityBetween(index, 1, 2).similarity;
    const weak = similarityBetween(index, 1, 3).similarity;
    expect(strong).toBeGreaterThan(weak);
    expect(strong).toBeGreaterThan(0);
  });

  it("opposite polarity decreases compatibility", () => {
    const works = [
      work(1, { concepts: [{ id: 1, weight: 80 }, { id: 2, weight: 60 }] }),
      work(2, { concepts: [{ id: 1, weight: 80 }, { id: 2, weight: 60 }] }),
      work(3, { concepts: [{ id: 1, weight: 80 }, { id: 2, weight: 60, polarity: -1 }] }),
    ];
    const index = buildFeatureIndex(works, settings);
    const aligned = similarityBetween(index, 1, 2).similarity;
    const opposed = similarityBetween(index, 1, 3).similarity;
    expect(opposed).toBeLessThan(aligned);
  });

  it("negative shared evidence can make similarity non-positive", () => {
    const works = [
      work(1, { concepts: [{ id: 1, weight: 90 }] }),
      work(2, { concepts: [{ id: 1, weight: 90, polarity: -1 }] }),
    ];
    const index = buildFeatureIndex(works, settings);
    expect(similarityBetween(index, 1, 2).similarity).toBeLessThan(0);
  });

  it("generic concepts contribute less than rare ones", () => {
    const generic = { id: 1, weight: 80 };
    const works = [
      work(1, { concepts: [generic, { id: 2, weight: 80 }] }),
      work(2, { concepts: [generic, { id: 2, weight: 80 }] }),
      work(3, { concepts: [generic, { id: 3, weight: 80 }] }),
      work(4, { concepts: [generic, { id: 3, weight: 80 }] }),
      work(5, { concepts: [generic] }),
      work(6, { concepts: [generic] }),
    ];
    const index = buildFeatureIndex(works, settings);
    const viaRare = similarityBetween(index, 1, 2);
    const viaGenericOnly = similarityBetween(index, 1, 5);
    expect(viaRare.similarity).toBeGreaterThan(viaGenericOnly.similarity);
    const factors = viaRare.topFactors;
    expect(factors[0].id).toBe("concept:2");
  });

  it("similarityBetween reports sharedFeatureCount and labeled topFactors", () => {
    const works = [
      work(1, {
        concepts: [{ id: 1, label: "Cyberpunk", weight: 90 }],
        contributors: [{ entityId: 50, label: "R. Scott", role: "director", weight: 80 }],
      }),
      work(2, {
        concepts: [{ id: 1, label: "Cyberpunk", weight: 70 }],
        contributors: [{ entityId: 50, label: "R. Scott", role: "director", weight: 80 }],
      }),
      work(3, { concepts: [{ id: 9, weight: 50 }] }),
    ];
    const index = buildFeatureIndex(works, settings);
    const result = similarityBetween(index, 1, 2);
    expect(result.sharedFeatureCount).toBe(2);
    expect(result.topFactors.map((f) => f.label)).toContain("Cyberpunk");
    expect(result.topFactors.find((f) => f.id === "entity:50")?.source).toBe("contributor");
  });

  it("candidate generation is bounded by the DF cap and allowed set", () => {
    const shared = { id: 1, weight: 80 };
    const works: WorkViewModel[] = [];
    for (let i = 1; i <= CANDIDATE_FEATURE_DF_CAP + 10; i += 1) {
      works.push(work(i, { concepts: [shared] }));
    }
    works.push(work(500, { concepts: [shared, { id: 2, weight: 80 }] }));
    works.push(work(501, { concepts: [{ id: 2, weight: 60 }] }));
    const index = buildFeatureIndex(works, settings);
    // concept:1 df > cap → only concept:2 generates candidates
    expect([...similarityCandidates(index, 500)]).toEqual([501]);
    expect([...similarityCandidates(index, 500, new Set([1, 2]))]).toEqual([]);
  });

  it("deterministic: same input twice gives deeply equal results", () => {
    const works = [
      work(1, { concepts: [{ id: 1, weight: 80 }, { id: 2, weight: 40, polarity: -1 }] }),
      work(2, { concepts: [{ id: 1, weight: 70 }, { id: 2, weight: 20 }] }),
    ];
    const a = buildFeatureIndex(works, settings);
    const b = buildFeatureIndex(works, settings);
    expect(similarityBetween(a, 1, 2)).toEqual(similarityBetween(b, 1, 2));
    expect([...a.vectors.get(1)!.entries()]).toEqual([...b.vectors.get(1)!.entries()]);
  });
});

describe("factorPhrase", () => {
  it("phrases each source type", () => {
    expect(factorPhrase({ source: "direct-concept", label: "Thriller", category: "Genre" })).toBe(
      "Shared genre: Thriller",
    );
    expect(factorPhrase({ source: "direct-concept", label: "Thriller" })).toBe("Shared concept: Thriller");
    expect(factorPhrase({ source: "contributor", label: "David Lynch", relationType: "director" })).toBe(
      "Same director: David Lynch",
    );
    expect(factorPhrase({ source: "organization", label: "A24", relationType: "production_company" })).toBe(
      "Shared production company: A24",
    );
    expect(factorPhrase({ source: "content-guide", label: "Violence" })).toBe("Similar content advisory: Violence");
  });
});

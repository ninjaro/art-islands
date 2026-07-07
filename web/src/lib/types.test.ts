import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, mergeSettings } from "./types";

describe("mergeSettings", () => {
  it("fills every section with defaults", () => {
    const s = mergeSettings({});
    expect(s.features.directorMultiplier).toBe(0.5);
    expect(s.features.directConceptMultiplier).toBe(1.0);
    expect(s.browse.defaultPageSize).toBe(50);
    expect(s.browse.pageSizeOptions).toEqual([25, 50, 100]);
    expect(s.evolution.kindMismatchFactor).toBe(0.6);
    expect(s.islands.maxInferredNeighborsPerNode).toBe(8);
  });

  it("migrates legacy setting names", () => {
    const s = mergeSettings({
      islands: { maxNeighborsPerSeed: 12 },
      evolution: { minimumSharedTags: 3 },
    });
    expect(s.islands.maxInferredNeighborsPerNode).toBe(12);
    expect(s.evolution.minimumSharedFeatures).toBe(3);
  });

  it("prefers the new name when both are present", () => {
    const s = mergeSettings({ islands: { maxNeighborsPerSeed: 12, maxInferredNeighborsPerNode: 6 } });
    expect(s.islands.maxInferredNeighborsPerNode).toBe(6);
  });

  it("rejects invalid values and non-numeric page sizes", () => {
    const s = mergeSettings({
      features: { directorMultiplier: -1 },
      browse: { defaultPageSize: 37, pageSizeOptions: ["a", 10] },
    });
    expect(s.features.directorMultiplier).toBe(0.5);
    expect(s.browse.pageSizeOptions).toEqual([25, 50, 100]);
    expect(s.browse.defaultPageSize).toBe(50);
  });

  it("keeps a valid custom page size that is in the options", () => {
    const s = mergeSettings({ browse: { defaultPageSize: 100 } });
    expect(s.browse.defaultPageSize).toBe(100);
  });

  it("does not mutate the defaults object", () => {
    mergeSettings({ browse: { pageSizeOptions: [10, 20] } });
    expect(DEFAULT_SETTINGS.browse.pageSizeOptions).toEqual([25, 50, 100]);
  });
});

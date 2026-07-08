import { describe, expect, it } from "vitest";
import { validateV2Data } from "./data";

const validParts = () => ({
  catalog: [],
  entities: {},
  entityTypes: { definitions: [], assignments: [] },
  relations: [],
  concepts: { categories: [], concepts: [], entityConcepts: [] },
  advisories: { categories: [], advisories: [] },
  ratings: { systems: [], ratings: [] },
  restrictions: [],
});

describe("validateV2Data", () => {
  it("accepts a complete export set", () => {
    const result = validateV2Data(validParts());
    expect("data" in result).toBe(true);
  });

  it("reports missing required files", () => {
    const result = validateV2Data({ ...validParts(), catalog: null });
    expect(result).toEqual({ missing: ["v2/catalog.json"], invalid: [] });
  });

  it("reports structurally invalid required files", () => {
    const result = validateV2Data({ ...validParts(), concepts: [] });
    expect(result).toEqual({ missing: [], invalid: ["v2/concepts.json"] });
  });

  it("defaults absent optional files to valid empty states", () => {
    const result = validateV2Data({
      ...validParts(),
      advisories: null,
      ratings: null,
      restrictions: null,
    });
    expect("data" in result).toBe(true);
    if ("data" in result) {
      expect(result.data.advisories).toEqual({ categories: [], advisories: [] });
      expect(result.data.ratings).toEqual({ systems: [], ratings: [] });
      expect(result.data.restrictions).toEqual([]);
    }
  });

  it("rejects malformed optional files instead of silently dropping them", () => {
    const result = validateV2Data({ ...validParts(), advisories: [1, 2, 3] });
    expect(result).toEqual({ missing: [], invalid: ["v2/advisories.json"] });
  });
});

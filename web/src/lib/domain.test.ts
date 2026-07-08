import { describe, expect, it } from "vitest";
import { broadKindForType, buildDomainModel, roleLabel } from "./domain";
import type { V2Data } from "./types";

function fixture(): V2Data {
  return {
    catalog: [
      {
        id: 1,
        label: "Test Film",
        family: "work",
        image: "film.jpg",
        compatibilityDate: "1977-05-01",
        compatibilityDatePrecision: 2,
        dates: [
          { type: "publication", value: "1977-05-01", precision: 2, primary: true, rank: "compat" },
          { type: "inception", value: "1975-01-01", precision: 1, primary: false },
        ],
        measurements: [
          { type: "duration", number: 8220, unit: "seconds", confidence: 0.9 },
          { type: "episode_count", number: 3 },
        ],
      },
      { id: 2, label: "Test Album", family: "work", compatibilityDate: "1980-01-01", compatibilityDatePrecision: 1 },
      { id: 9, label: "Bare Work", family: "work" },
    ],
    entities: {
      "1": { id: 1, label: "Test Film", family: "work", catalogued: true, description: "A film about tests." },
      "2": { id: 2, label: "Test Album", family: "work", catalogued: true },
      "9": { id: 9, label: "Bare Work", family: "work", catalogued: true },
      "50": {
        id: 50,
        label: "Rita Director",
        family: "person",
        catalogued: false,
        identifiers: [{ scheme: "imdb_name", value: "nm0000001", primary: true }],
      },
      "60": { id: 60, label: "Big Studio", family: "organization", catalogued: false },
    },
    entityTypes: {
      definitions: [
        { id: 1, code: "film", family: "work", label: "Film", description: null },
        { id: 2, code: "music_album", family: "work", label: "Music album", description: null },
        { id: 3, code: "person", family: "person", label: "Person", description: null },
      ],
      assignments: [
        { entityId: 1, typeId: 1, isPrimary: 1, confidence: 1 },
        { entityId: 2, typeId: 2, isPrimary: 1, confidence: 1 },
        { entityId: 50, typeId: 3, isPrimary: 1, confidence: 1 },
      ],
    },
    relations: [
      { id: 1, source: 1, target: 50, type: "director", weight: 80, polarity: 0 },
      { id: 2, source: 1, target: 60, type: "production_company", weight: 40, polarity: 0 },
      { id: 3, source: 1, target: 50, type: "cast_member", weight: 30, polarity: 0 },
      { id: 4, source: 2, target: 1, type: "adapted_from", weight: 70, polarity: 0 },
    ],
    concepts: {
      categories: [
        { id: 1, code: "genre", label: "Genre" },
        { id: 3, code: "theme", label: "Theme" },
      ],
      concepts: [
        { id: 100, label: "Horror", category: "genre" },
        { id: 101, label: "Dreams", category: "theme" },
        { id: 102, label: "Romance", category: "mystery_category" },
      ],
      entityConcepts: [
        { entityId: 1, conceptId: 101, weight: 55, polarity: -1, confidence: null },
        { entityId: 1, conceptId: 100, weight: 80, polarity: 0, confidence: null },
        { entityId: 1, conceptId: 102, weight: null, polarity: 0, confidence: null },
      ],
    },
    advisories: {
      categories: [{ code: "violence", label: "Violence" }],
      advisories: [{ entityId: 1, categoryCode: "violence", intensity: 62, uncertainty: 10 }],
    },
    restrictions: [
      { id: 1, entityId: 1, countryCode: "GB", restrictionType: "refused_classification", status: "historical" },
    ],
  };
}

describe("buildDomainModel", () => {
  const model = buildDomainModel(fixture());
  const film = model.workById.get(1)!;

  it("normalizes concepts grouped and sorted by weight then label with null weights last", () => {
    expect(film.concepts.map((c) => c.conceptId)).toEqual([100, 101, 102]);
    expect(film.conceptsByCategory.genre[0].label).toBe("Horror");
    expect(film.conceptsByCategory.genre[0].categoryLabel).toBe("Genre");
  });

  it("keeps unknown concept categories under other", () => {
    expect(film.conceptsByCategory.other.map((c) => c.conceptId)).toEqual([102]);
    expect(film.conceptsByCategory.other[0].categoryLabel).toBe("Other");
  });

  it("groups contributors by role with human role labels", () => {
    expect(film.contributorsByRole.director.map((c) => c.label)).toEqual(["Rita Director"]);
    expect(roleLabel("cast_member")).toBe("Cast");
    expect(roleLabel("some_new_role")).toBe("Some new role");
  });

  it("derives duration from seconds and formats it", () => {
    expect(film.duration).toEqual({ seconds: 8220, label: "2 h 17 min" });
    expect(film.measurements).toHaveLength(2);
  });

  it("picks the primary date and falls back to compatibilityDate", () => {
    expect(film.primaryDate?.value).toBe("1977-05-01");
    expect(film.sortDate).toBe("1977-05-01");
    expect(film.year).toBe(1977);
    const album = model.workById.get(2)!;
    expect(album.primaryDate?.type).toBe("compatibility");
    expect(album.year).toBe(1980);
  });

  it("maps primary entity type to broadKind", () => {
    expect(film.type).toBe("film");
    expect(film.typeLabel).toBe("Film");
    expect(film.broadKind).toBe("film");
    expect(broadKindForType("television_series")).toBe("tv");
    expect(broadKindForType("music_album")).toBe("music");
    expect(broadKindForType("video_game")).toBe("game");
    expect(broadKindForType("other_creative_work")).toBe("work");
  });

  it("collects work-to-work relations only", () => {
    expect(model.workRelations.map((r) => r.id)).toEqual([4]);
  });

  it("normalizes advisories with category labels", () => {
    expect(film.advisories[0]).toMatchObject({ categoryCode: "violence", category: "Violence", intensity: 62 });
  });

  it("normalizes restrictions and identifiers", () => {
    expect(film.restrictions[0].type).toBe("refused_classification");
    const contributor = film.contributors.find((c) => c.entityId === 50)!;
    expect(contributor.family).toBe("person");
    expect(model.entityById.get(50)?.identifiers?.[0].scheme).toBe("imdb_name");
  });

  it("produces valid empty states when optional data is missing", () => {
    const bare = model.workById.get(9)!;
    expect(bare.concepts).toEqual([]);
    expect(bare.contributors).toEqual([]);
    expect(bare.duration).toBeUndefined();
    expect(bare.advisories).toEqual([]);
    expect(bare.sortDate).toBeNull();
    expect(bare.year).toBeNull();
    expect(bare.broadKind).toBe("work");
  });

  it("exposes type options with counts", () => {
    expect(model.typeOptions).toEqual([
      { code: "film", label: "Film", count: 1 },
      { code: "music_album", label: "Music album", count: 1 },
      { code: "other_creative_work", label: "Work", count: 1 },
    ]);
  });

  it("carries the entity description onto the work", () => {
    expect(film.description).toBe("A film about tests.");
  });
});

import { describe, expect, it } from "vitest";
import { EMPTY_FILTERS, filterWorks, relevanceScores, sortWorks } from "./browse";
import { buildFeatureIndex } from "./features";
import { makeDomain, makeWork } from "./testFixtures";
import { DEFAULT_SETTINGS } from "./types";

const works = [
  makeWork(1, {
    label: "Alpha Film",
    date: "1980-01-01",
    concepts: [{ id: 10, label: "Horror", weight: 90 }],
    contributors: [{ entityId: 50, label: "Rita Director", role: "director", weight: 80 }],
  }),
  makeWork(2, {
    label: "Beta Album",
    date: "1990-01-01",
    concepts: [{ id: 20, label: "Progressive", weight: 80 }],
  }),
  makeWork(3, {
    label: "Gamma Film",
    date: "1970-01-01",
    concepts: [{ id: 10, label: "Horror", weight: 30 }],
  }),
  makeWork(4, {
    label: "Delta Feature",
    date: "2000-01-01",
    concepts: [{ id: 10, label: "Horror", weight: 90, polarity: -1 }],
  }),
];
works[1].type = "music_album";
works[1].typeLabel = "Music album";
const domain = makeDomain(works);
const index = buildFeatureIndex(works, DEFAULT_SETTINGS.features);

describe("filterWorks", () => {
  it("filters by type, date range, and concept", () => {
    expect(filterWorks(domain, { ...EMPTY_FILTERS, type: "music_album" }).map((w) => w.id)).toEqual([2]);
    expect(filterWorks(domain, { ...EMPTY_FILTERS, minDate: "1985-01-01" }).map((w) => w.id)).toEqual([2, 4]);
    expect(filterWorks(domain, { ...EMPTY_FILTERS, maxDate: "1975-01-01" }).map((w) => w.id)).toEqual([3]);
    expect(filterWorks(domain, { ...EMPTY_FILTERS, conceptId: "20" }).map((w) => w.id)).toEqual([2]);
  });

  it("matches queries against labels, concept labels, and contributor names", () => {
    expect(filterWorks(domain, { ...EMPTY_FILTERS, q: "beta" }).map((w) => w.id)).toEqual([2]);
    expect(filterWorks(domain, { ...EMPTY_FILTERS, q: "horror" }).map((w) => w.id)).toEqual([1, 3, 4]);
    expect(filterWorks(domain, { ...EMPTY_FILTERS, q: "rita" }).map((w) => w.id)).toEqual([1]);
  });
});

describe("sortWorks", () => {
  it("date/label/kind sorts stay literal and ignore relevance", () => {
    const relevance = new Map([[3, 100]]);
    expect(sortWorks(works, "date", relevance).map((w) => w.id)).toEqual([3, 1, 2, 4]);
    expect(sortWorks(works, "label", relevance).map((w) => w.id)).toEqual([1, 2, 4, 3]);
    expect(sortWorks(works, "kind", relevance).map((w) => w.id)).toEqual([1, 4, 3, 2]);
  });

  it("relevance ranks higher-weight matches first and negative polarity last", () => {
    const filters = { ...EMPTY_FILTERS, q: "horror" };
    const matched = filterWorks(domain, filters);
    const scores = relevanceScores(index, matched, filters)!;
    const sorted = sortWorks(matched, "relevance", scores).map((w) => w.id);
    expect(sorted[0]).toBe(1); // weight 90 beats weight 30
    expect(sorted[sorted.length - 1]).toBe(4); // negative polarity sinks
  });

  it("concept filter relevance uses the feature value", () => {
    const filters = { ...EMPTY_FILTERS, conceptId: "10" };
    const matched = filterWorks(domain, filters);
    const scores = relevanceScores(index, matched, filters)!;
    expect(scores.get(1)!).toBeGreaterThan(scores.get(3)!);
    expect(scores.get(4)!).toBeLessThan(0);
  });

  it("relevance is null without a query or concept filter", () => {
    expect(relevanceScores(index, works, EMPTY_FILTERS)).toBeNull();
  });
});

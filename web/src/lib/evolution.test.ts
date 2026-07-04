import { describe, expect, test } from "vitest";
import { buildForest, groupChildren, revealWork } from "./evolution";
import { buildVisibleForest, layoutForest } from "./evolutionLayout";
import { buildTagIndex } from "./tagIndex";
import type { CatalogItem, EvolutionExport, EvolutionSettings, TagEntry } from "./types";
import { DEFAULT_SETTINGS } from "./types";

function work(id: number, kind: number, tags: TagEntry[], date = "1980-01-01"): CatalogItem {
  return { id, label: `Work ${id}`, kind, date, datePrecision: 3, image: null, refs: [], tags, links: [] };
}

const settings: EvolutionSettings = {
  ...DEFAULT_SETTINGS.evolution,
  visibleChildrenPerNode: 2,
  groupingSimilarity: 0.3,
};

function makeExport(nodes: Array<[number, number | null, number]>): EvolutionExport {
  return {
    version: 1,
    note: "test",
    nodes: nodes.map(([id, parent, score]) => ({ id, parent, score, shared: 2, topTags: [] })),
  };
}

describe("buildForest", () => {
  test("ranks roots by subtree size and sorts children by score", () => {
    const forest = buildForest(
      makeExport([
        [1, null, 0],
        [2, 1, 0.5],
        [3, 1, 0.9],
        [4, 3, 0.4],
        [10, null, 0],
      ]),
    );
    expect(forest.roots).toEqual([1, 10]);
    expect(forest.childrenByParent.get(1)!.map((child) => child.id)).toEqual([3, 2]);
    expect(forest.subtreeSizes.get(1)).toBe(4);
    expect(forest.subtreeSizes.get(10)).toBe(1);
  });
});

describe("groupChildren placeholders", () => {
  // Parent 1 with six children: two strong visible, the rest hidden.
  // Hidden: 4,5 are similar films; 6 is an unrelated film; 7 is music.
  const catalog = [
    work(1, 1, [[10, 100, 0]]),
    work(2, 1, [[10, 100, 0]]),
    work(3, 1, [[10, 100, 0]]),
    work(4, 1, [[20, 100, 0], [21, 100, 0]]),
    work(5, 1, [[20, 100, 0], [21, 90, 0]]),
    work(6, 1, [[30, 100, 0], [31, 100, 0]]),
    work(7, 2, [[20, 100, 0], [21, 100, 0]]),
  ];
  const index = buildTagIndex(catalog);
  const catalogById = new Map(catalog.map((item) => [item.id, item]));
  const children = [
    { id: 2, score: 0.9, shared: 2, topTags: [] },
    { id: 3, score: 0.8, shared: 2, topTags: [] },
    { id: 4, score: 0.5, shared: 2, topTags: [] },
    { id: 5, score: 0.4, shared: 2, topTags: [] },
    { id: 6, score: 0.3, shared: 2, topTags: [] },
    { id: 7, score: 0.2, shared: 2, topTags: [] },
  ];

  test("shows only the strongest children and groups the rest", () => {
    const { visible, placeholders } = groupChildren(1, children, catalogById, index, settings, new Set());
    expect(visible.map((child) => child.id)).toEqual([2, 3]);
    const allHidden = placeholders.flatMap((placeholder) => placeholder.childIds);
    expect(allHidden.sort()).toEqual([4, 5, 6, 7]);
  });

  test("placeholders contain only real siblings of the same kind with similar profiles", () => {
    const { placeholders } = groupChildren(1, children, catalogById, index, settings, new Set());
    // 4 and 5 share a profile and a kind; 6 (unrelated tags) and 7 (music)
    // must not join their group.
    const groupWith4 = placeholders.find((placeholder) => placeholder.childIds.includes(4));
    expect(groupWith4).toBeDefined();
    expect(groupWith4!.childIds).toEqual([4, 5]);
    expect(groupWith4!.kind).toBe("film");

    const groupWith6 = placeholders.find((placeholder) => placeholder.childIds.includes(6));
    expect(groupWith6!.childIds).toEqual([6]);

    const groupWith7 = placeholders.find((placeholder) => placeholder.childIds.includes(7));
    expect(groupWith7!.childIds).toEqual([7]);
    expect(groupWith7!.kind).toBe("music");

    expect(placeholders).toHaveLength(3);
  });

  test("expanding a placeholder returns exactly its hidden entity ids", () => {
    const collapsed = groupChildren(1, children, catalogById, index, settings, new Set());
    const groupWith4 = collapsed.placeholders.find((placeholder) => placeholder.childIds.includes(4))!;

    const expanded = groupChildren(1, children, catalogById, index, settings, new Set([groupWith4.key]));
    expect(expanded.visible.map((child) => child.id)).toEqual([2, 3, 4, 5]);
    const remainingHidden = expanded.placeholders.flatMap((placeholder) => placeholder.childIds);
    expect(remainingHidden.sort()).toEqual([6, 7]);
  });

  test("does not create a placeholder to hide a single overflow child", () => {
    const short = children.slice(0, 3);
    const { visible, placeholders } = groupChildren(1, short, catalogById, index, settings, new Set());
    expect(visible.map((child) => child.id)).toEqual([2, 3, 4]);
    expect(placeholders).toEqual([]);
  });

  test("visible forest layout is deterministic", () => {
    const forest = buildForest(
      makeExport([
        [1, null, 0],
        [2, 1, 0.5],
        [3, 1, 0.9],
        [4, 3, 0.4],
      ]),
    );
    const state = {
      expandedNodes: new Set([1, 3]),
      expandedGroups: new Set<string>(),
      visibleRootCount: 20,
      pinnedRoots: new Set<number>(),
    };
    const first = layoutForest(buildVisibleForest(forest, catalogById, index, settings, state));
    const second = layoutForest(buildVisibleForest(forest, catalogById, index, settings, state));
    expect(first).toEqual(second);
    expect(first.nodes.length).toBe(4);
    expect(first.edges.length).toBe(3);
  });

  test("revealWork expands the ancestor chain and hiding groups", () => {
    const forest = buildForest(
      makeExport([
        [1, null, 0],
        [2, 1, 0.9],
        [3, 1, 0.8],
        [4, 1, 0.5],
        [5, 1, 0.4],
        [6, 1, 0.3],
        [7, 1, 0.2],
        [8, 4, 0.6],
      ]),
    );
    const reveal = revealWork(8, forest, catalogById, index, settings);
    expect(reveal).not.toBeNull();
    expect(reveal!.rootId).toBe(1);
    expect(reveal!.expandNodes).toEqual([1, 4]);
    // 4 is hidden behind a placeholder under 1 (visible limit 2), so its
    // group must be expanded for 8 to become reachable.
    expect(reveal!.expandGroups.length).toBe(1);
  });
});

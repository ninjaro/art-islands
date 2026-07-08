import { describe, expect, test } from "vitest";
import { buildForest, groupChildren, revealWork } from "./evolution";
import type { EvolutionChild } from "./evolution";
import { buildVisibleForest, layoutForest } from "./evolutionLayout";
import { buildFeatureIndex } from "./features";
import { makeDomain, makeWork } from "./testFixtures";
import type { EvolutionExport, EvolutionSettings } from "./types";
import { DEFAULT_SETTINGS } from "./types";

const settings: EvolutionSettings = {
  ...DEFAULT_SETTINGS.evolution,
  visibleChildrenPerNode: 2,
  groupingSimilarity: 0.3,
};

function makeExport(nodes: Array<[number, number | null, number]>): EvolutionExport {
  return {
    version: 2,
    note: "test",
    nodes: nodes.map(([id, parent, score]) => ({
      id,
      parent,
      evidence: { score, sharedFeatureCount: 2, topFactors: [] },
    })),
  };
}

function child(id: number, score: number): EvolutionChild {
  return { id, evidence: { score, sharedFeatureCount: 2, topFactors: [] } };
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
    expect(forest.childrenByParent.get(1)!.map((entry) => entry.id)).toEqual([3, 2]);
    expect(forest.subtreeSizes.get(1)).toBe(4);
    expect(forest.subtreeSizes.get(10)).toBe(1);
  });
});

describe("groupChildren placeholders", () => {
  // Parent 1 with six children: two strong visible, the rest hidden.
  // Hidden: 4,5 are similar films; 6 is an unrelated film; 7 is music.
  const works = [
    makeWork(1, { date: "1950-01-01", concepts: [{ id: 10, weight: 100 }] }),
    makeWork(2, { date: "1960-01-01", concepts: [{ id: 10, weight: 100 }] }),
    makeWork(3, { date: "1961-01-01", concepts: [{ id: 10, weight: 100 }] }),
    makeWork(4, { date: "1962-01-01", concepts: [{ id: 20, weight: 100 }, { id: 21, weight: 100 }] }),
    makeWork(5, { date: "1963-01-01", concepts: [{ id: 20, weight: 100 }, { id: 21, weight: 90 }] }),
    makeWork(6, { date: "1964-01-01", concepts: [{ id: 30, weight: 100 }, { id: 31, weight: 100 }] }),
    makeWork(7, {
      date: "1965-01-01",
      broadKind: "music",
      concepts: [{ id: 20, weight: 100 }, { id: 21, weight: 100 }],
    }),
  ];
  const domain = makeDomain(works);
  const index = buildFeatureIndex(works, DEFAULT_SETTINGS.features);
  const children = [
    child(2, 0.9),
    child(3, 0.8),
    child(4, 0.5),
    child(5, 0.4),
    child(6, 0.3),
    child(7, 0.2),
  ];

  test("shows only the strongest children and groups the rest", () => {
    const { visible, placeholders } = groupChildren(1, children, domain, index, settings, new Set());
    expect(visible.map((entry) => entry.id)).toEqual([2, 3]);
    const allHidden = placeholders.flatMap((placeholder) => placeholder.childIds);
    expect(allHidden.sort()).toEqual([4, 5, 6, 7]);
  });

  test("placeholders contain only real siblings of the same kind with similar profiles", () => {
    const { placeholders } = groupChildren(1, children, domain, index, settings, new Set());
    // 4 and 5 share a profile and a kind; 6 (unrelated concepts) and 7
    // (music) must not join their group.
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
    const collapsed = groupChildren(1, children, domain, index, settings, new Set());
    const groupWith4 = collapsed.placeholders.find((placeholder) => placeholder.childIds.includes(4))!;

    const expanded = groupChildren(1, children, domain, index, settings, new Set([groupWith4.key]));
    expect(expanded.visible.map((entry) => entry.id)).toEqual([2, 3, 4, 5]);
    const remainingHidden = expanded.placeholders.flatMap((placeholder) => placeholder.childIds);
    expect(remainingHidden.sort()).toEqual([6, 7]);
  });

  test("does not create a placeholder to hide a single overflow child", () => {
    const short = children.slice(0, 3);
    const { visible, placeholders } = groupChildren(1, short, domain, index, settings, new Set());
    expect(visible.map((entry) => entry.id)).toEqual([2, 3, 4]);
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
    const yearOf = (id: number) => domain.workById.get(id)?.year ?? null;
    const first = layoutForest(buildVisibleForest(forest, domain, index, settings, state), yearOf);
    const second = layoutForest(buildVisibleForest(forest, domain, index, settings, state), yearOf);
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
    const reveal = revealWork(8, forest, domain, index, settings);
    expect(reveal).not.toBeNull();
    expect(reveal!.rootId).toBe(1);
    expect(reveal!.expandNodes).toEqual([1, 4]);
    // 4 is hidden behind a placeholder under 1 (visible limit 2), so its
    // group must be expanded for 8 to become reachable.
    expect(reveal!.expandGroups.length).toBe(1);
  });
});

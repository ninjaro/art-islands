import { describe, expect, test } from "vitest";
import { buildIslandsGraph, connectedComponents } from "./islands";
import { layoutIslands } from "./islandsLayout";
import { buildTagIndex } from "./tagIndex";
import type { CatalogItem, LinkEntry, Settings, TagEntry } from "./types";
import { DEFAULT_SETTINGS } from "./types";

function work(id: number, tags: TagEntry[], links: LinkEntry[] = []): CatalogItem {
  return {
    id,
    label: `Work ${id}`,
    kind: 1,
    date: `19${String(10 + (id % 80)).padStart(2, "0")}-01-01`,
    datePrecision: 3,
    image: null,
    refs: [],
    tags,
    links,
  };
}

function settingsWith(overrides: Partial<Settings["islands"]> = {}): Settings {
  return {
    ...DEFAULT_SETTINGS,
    islands: { ...DEFAULT_SETTINGS.islands, ...overrides },
  };
}

describe("buildIslandsGraph", () => {
  // Cluster A: 1,2,3 share tags 10/11. Cluster B: 4,5 share tags 20/21.
  // No tags overlap across clusters.
  const catalog = [
    work(1, [[10, 100, 0], [11, 100, 0]]),
    work(2, [[10, 100, 0], [11, 90, 0]]),
    work(3, [[10, 90, 0], [11, 80, 0]]),
    work(4, [[20, 100, 0], [21, 100, 0]]),
    work(5, [[20, 90, 0], [21, 90, 0]]),
    work(6, [[30, 100, 0]]),
  ];
  const index = buildTagIndex(catalog);

  test("liked and disliked works are seeds; recommendations are gray and separate", () => {
    const graph = buildIslandsGraph(catalog, index, { "1": 1, "4": -1 }, settingsWith());
    const byId = new Map(graph.nodes.map((node) => [node.id, node]));
    expect(byId.get(1)?.state).toBe("liked");
    expect(byId.get(4)?.state).toBe("disliked");
    // 2 and 3 share liked tags: recommended.
    expect(byId.get(2)?.state).toBe("recommended");
    expect(byId.get(3)?.state).toBe("recommended");
    // Rated nodes are never duplicated as recommendations: exactly one node per id.
    const ids = graph.nodes.map((node) => node.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test("candidates require positive evidence", () => {
    const graph = buildIslandsGraph(catalog, index, { "1": 1 }, settingsWith());
    const ids = new Set(graph.nodes.map((node) => node.id));
    // 5 and 6 share nothing with the liked work: not displayed.
    expect(ids.has(5)).toBe(false);
    expect(ids.has(6)).toBe(false);
  });

  test("dislike overlap lowers recommendation score", () => {
    const withDislike = buildIslandsGraph(
      [...catalog, work(7, [[10, 100, 0], [40, 100, 0]]), work(8, [[10, 100, 0], [41, 100, 0]])],
      buildTagIndex([...catalog, work(7, [[10, 100, 0], [40, 100, 0]]), work(8, [[10, 100, 0], [41, 100, 0]])]),
      { "1": 1, "9": -1 },
      settingsWith(),
    );
    // Now add a dislike that shares tag 40 with work 7.
    const catalog2 = [...catalog, work(7, [[10, 100, 0], [40, 100, 0]]), work(8, [[10, 100, 0], [41, 100, 0]]), work(9, [[40, 100, 0]])];
    const graph2 = buildIslandsGraph(catalog2, buildTagIndex(catalog2), { "1": 1, "9": -1 }, settingsWith());
    const node7 = graph2.nodes.find((node) => node.id === 7);
    const node8 = graph2.nodes.find((node) => node.id === 8);
    expect(node8).toBeDefined();
    if (node7) {
      expect(node7.score!).toBeLessThan(node8!.score!);
    }
    expect(withDislike.nodes.length).toBeGreaterThan(0);
  });

  test("graph caps are respected", () => {
    const big: CatalogItem[] = [];
    for (let id = 1; id <= 60; id += 1) {
      big.push(work(id, [[10, 100, 0], [11, 100, 0], [(id % 6) + 50, 80, 0]]));
    }
    const bigIndex = buildTagIndex(big);
    const config = settingsWith({ maxRecommendationNodes: 10, maxEdges: 15, maxInferredNeighborsPerNode: 3 });
    const graph = buildIslandsGraph(big, bigIndex, { "1": 1, "2": -1 }, config);
    const recommended = graph.nodes.filter((node) => node.state === "recommended");
    expect(recommended.length).toBeLessThanOrEqual(10);
    expect(graph.edges.length).toBeLessThanOrEqual(15);
  });

  test("components come from real edges; disconnected clusters stay disconnected", () => {
    const graph = buildIslandsGraph(catalog, index, { "1": 1, "4": 1 }, settingsWith());
    const componentOf = new Map<number, number>();
    for (const component of graph.components) {
      for (const id of component.nodeIds) componentOf.set(id, component.index);
    }
    // Cluster A nodes together, cluster B nodes together, never merged.
    expect(componentOf.get(1)).toBe(componentOf.get(2));
    expect(componentOf.get(1)).toBe(componentOf.get(3));
    expect(componentOf.get(4)).toBe(componentOf.get(5));
    expect(componentOf.get(1)).not.toBe(componentOf.get(4));
    // No edge crosses components.
    for (const edge of graph.edges) {
      expect(componentOf.get(edge.source)).toBe(componentOf.get(edge.target));
    }
  });

  test("an isolated rated work forms a one-node island", () => {
    const graph = buildIslandsGraph(catalog, index, { "6": -1 }, settingsWith());
    expect(graph.nodes).toHaveLength(1);
    expect(graph.components).toHaveLength(1);
    expect(graph.components[0].nodeIds).toEqual([6]);
    expect(graph.edges).toHaveLength(0);
  });

  test("explicit relations are distinguishable from inferred similarity", () => {
    const linked = [
      work(1, [[10, 100, 0], [11, 100, 0]], [[2, 3, 50, 0]]),
      work(2, [[10, 100, 0], [11, 90, 0]]),
      work(3, [[10, 90, 0], [11, 80, 0]]),
    ];
    const linkedIndex = buildTagIndex(linked);
    const graph = buildIslandsGraph(linked, linkedIndex, { "1": 1 }, settingsWith());
    const explicit = graph.edges.find(
      (edge) => (edge.source === 1 && edge.target === 2) || (edge.source === 2 && edge.target === 1),
    );
    expect(explicit?.kind).toBe("explicit");
    expect(explicit?.linkKind).toBe(3);
    const inferred = graph.edges.find((edge) => edge.kind === "similarity");
    expect(inferred).toBeDefined();
    // Inferred edges carry an explanation.
    expect(inferred!.sharedTagCount).toBeGreaterThan(0);
    expect(inferred!.topTags.length).toBeGreaterThan(0);
    expect(inferred!.similarity).toBeGreaterThan(0);
  });

  test("deterministic graph and layout for identical inputs", () => {
    const ratings = { "1": 1, "4": -1 } as const;
    const first = buildIslandsGraph(catalog, index, ratings, settingsWith());
    const second = buildIslandsGraph(catalog, index, ratings, settingsWith());
    expect(first).toEqual(second);
    const layoutA = layoutIslands(first);
    const layoutB = layoutIslands(second);
    expect([...layoutA.positions.entries()]).toEqual([...layoutB.positions.entries()]);
    expect(layoutA.boxes).toEqual(layoutB.boxes);
  });

  test("layout keeps separate components spatially separate", () => {
    const graph = buildIslandsGraph(catalog, index, { "1": 1, "4": 1 }, settingsWith());
    const layout = layoutIslands(graph);
    expect(layout.boxes.length).toBe(graph.components.length);
    // Boxes must not overlap.
    for (const a of layout.boxes) {
      for (const b of layout.boxes) {
        if (a.index === b.index) continue;
        const overlap =
          a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
        expect(overlap).toBe(false);
      }
    }
  });
});

describe("connectedComponents", () => {
  test("computes components from explicit edge list only", () => {
    const nodes = [1, 2, 3, 4].map((id) => ({ id, state: "liked" as const }));
    const edges = [
      { source: 1, target: 2, kind: "similarity" as const, similarity: 1, sharedTagCount: 1, topTags: [] },
    ];
    const components = connectedComponents(nodes, edges);
    expect(components.map((component) => component.nodeIds)).toEqual([[1, 2], [3], [4]]);
  });
});

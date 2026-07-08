import { describe, expect, test } from "vitest";
import { buildFeatureIndex } from "./features";
import { buildIslandsGraph, connectedComponents } from "./islands";
import { layoutIslands } from "./islandsLayout";
import { makeDomain, makeWork } from "./testFixtures";
import type { Settings, V2Relation } from "./types";
import { DEFAULT_SETTINGS } from "./types";

type Spec = Parameters<typeof makeWork>[1];

function conceptWork(id: number, conceptEntries: Array<[number, number] | [number, number, number]>): Spec {
  return {
    date: `19${String(10 + (id % 80)).padStart(2, "0")}-01-01`,
    concepts: conceptEntries.map(([conceptId, weight, polarity]) => ({ id: conceptId, weight, polarity })),
  };
}

function build(
  specs: Record<number, Spec>,
  ratings: Record<string, 1 | -1>,
  settings: Settings,
  relations: V2Relation[] = [],
) {
  const works = Object.entries(specs).map(([id, spec]) => makeWork(Number(id), spec));
  const domain = makeDomain(works, relations);
  const index = buildFeatureIndex(works, settings.features);
  return buildIslandsGraph(domain, index, ratings, settings);
}

function settingsWith(overrides: Partial<Settings["islands"]> = {}): Settings {
  return {
    ...DEFAULT_SETTINGS,
    islands: { ...DEFAULT_SETTINGS.islands, ...overrides },
  };
}

// Cluster A: 1,2,3 share concepts 10/11. Cluster B: 4,5 share concepts 20/21.
// No concepts overlap across clusters. 6 is isolated.
const CATALOG: Record<number, Spec> = {
  1: conceptWork(1, [[10, 100], [11, 100]]),
  2: conceptWork(2, [[10, 100], [11, 90]]),
  3: conceptWork(3, [[10, 90], [11, 80]]),
  4: conceptWork(4, [[20, 100], [21, 100]]),
  5: conceptWork(5, [[20, 90], [21, 90]]),
  6: conceptWork(6, [[30, 100]]),
};

describe("buildIslandsGraph", () => {
  test("liked and disliked works are seeds; recommendations are separate", () => {
    const graph = build(CATALOG, { "1": 1, "4": -1 }, settingsWith());
    const byId = new Map(graph.nodes.map((node) => [node.id, node]));
    expect(byId.get(1)?.state).toBe("liked");
    expect(byId.get(4)?.state).toBe("disliked");
    // 2 and 3 share liked concepts: recommended, with evidence attached.
    expect(byId.get(2)?.state).toBe("recommended");
    expect(byId.get(3)?.state).toBe("recommended");
    expect(byId.get(2)?.topFactors?.length).toBeGreaterThan(0);
    // Rated nodes are never duplicated as recommendations: exactly one node per id.
    const ids = graph.nodes.map((node) => node.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test("candidates require positive evidence", () => {
    const graph = build(CATALOG, { "1": 1 }, settingsWith());
    const ids = new Set(graph.nodes.map((node) => node.id));
    // 5 and 6 share nothing with the liked work: not displayed.
    expect(ids.has(5)).toBe(false);
    expect(ids.has(6)).toBe(false);
  });

  test("each node selects at most K inferred neighbors (union bound)", () => {
    // 14 works, all pairwise similar: a complete graph would have 91 edges.
    const specs: Record<number, Spec> = {};
    for (let id = 1; id <= 14; id += 1) {
      specs[id] = conceptWork(id, [[10, 100], [11, 90 - id], [50 + (id % 5), 60]]);
    }
    const ratings = Object.fromEntries([...Array(14).keys()].map((i) => [String(i + 1), 1])) as Record<string, 1>;
    const k = 3;
    const graph = build(specs, ratings, settingsWith({ maxInferredNeighborsPerNode: k, minimumSimilarity: 0.01 }));
    const inferred = graph.edges.filter((edge) => edge.kind === "similarity");
    // Union of per-node selections: at most N*K edges, far below all-pairs.
    expect(inferred.length).toBeLessThanOrEqual(14 * k);
    expect(inferred.length).toBeLessThan(91);
    // The union may give single nodes more than K incident edges; that is
    // acceptable as long as the total stays bounded by per-node selection.
    const incident = new Map<number, number>();
    for (const edge of inferred) {
      incident.set(edge.source, (incident.get(edge.source) || 0) + 1);
      incident.set(edge.target, (incident.get(edge.target) || 0) + 1);
    }
    expect(Math.max(...incident.values())).toBeGreaterThanOrEqual(k);
  });

  test("no inferred edge from non-positive similarity", () => {
    const graph = build(
      {
        1: conceptWork(1, [[10, 90]]),
        2: conceptWork(2, [[10, 90, -1]]),
      },
      { "1": 1, "2": -1 },
      settingsWith({ minimumSimilarity: 0 }),
    );
    expect(graph.edges).toHaveLength(0);
    expect(graph.components).toHaveLength(2);
  });

  test("graph caps are respected", () => {
    const specs: Record<number, Spec> = {};
    for (let id = 1; id <= 60; id += 1) {
      specs[id] = conceptWork(id, [[10, 100], [11, 100], [(id % 6) + 50, 80]]);
    }
    const config = settingsWith({ maxRecommendationNodes: 10, maxEdges: 15, maxInferredNeighborsPerNode: 3 });
    const graph = build(specs, { "1": 1, "2": -1 }, config);
    const recommended = graph.nodes.filter((node) => node.state === "recommended");
    expect(recommended.length).toBeLessThanOrEqual(10);
    expect(graph.edges.length).toBeLessThanOrEqual(15);
  });

  test("components come from real edges; disconnected clusters stay disconnected", () => {
    const graph = build(CATALOG, { "1": 1, "4": 1 }, settingsWith());
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
    const graph = build(CATALOG, { "6": -1 }, settingsWith());
    expect(graph.nodes).toHaveLength(1);
    expect(graph.components).toHaveLength(1);
    expect(graph.components[0].nodeIds).toEqual([6]);
    expect(graph.edges).toHaveLength(0);
  });

  test("explicit relations carry their type and survive outside the K nearest", () => {
    // Work 1 and 6 share no concepts, but an explicit relation connects them.
    const relations: V2Relation[] = [{ id: 1, source: 1, target: 6, type: "adapted_from", weight: 50, polarity: 0 }];
    const graph = build(CATALOG, { "1": 1, "6": 1 }, settingsWith({ maxInferredNeighborsPerNode: 1 }), relations);
    const explicit = graph.edges.find((edge) => edge.kind === "explicit");
    expect(explicit).toBeDefined();
    expect(explicit).toMatchObject({ source: 1, target: 6, relationType: "adapted_from" });
    const inferred = graph.edges.find((edge) => edge.kind === "similarity");
    expect(inferred).toBeDefined();
    // Inferred edges carry an explanation.
    expect(inferred!.sharedFeatureCount).toBeGreaterThan(0);
    expect(inferred!.topFactors.length).toBeGreaterThan(0);
    expect(inferred!.similarity).toBeGreaterThan(0);
  });

  test("explicit edges win the global cap over inferred ones", () => {
    const relations: V2Relation[] = [{ id: 1, source: 1, target: 6, type: "adapted_from", weight: 50, polarity: 0 }];
    const graph = build(CATALOG, { "1": 1, "6": 1 }, settingsWith({ maxEdges: 1 }), relations);
    expect(graph.edges).toHaveLength(1);
    expect(graph.edges[0].kind).toBe("explicit");
  });

  test("deterministic graph and layout for identical inputs", () => {
    const ratings = { "1": 1, "4": -1 } as const;
    const first = build(CATALOG, ratings, settingsWith());
    const second = build(CATALOG, ratings, settingsWith());
    expect(first).toEqual(second);
    const layoutA = layoutIslands(first);
    const layoutB = layoutIslands(second);
    expect([...layoutA.positions.entries()]).toEqual([...layoutB.positions.entries()]);
    expect(layoutA.boxes).toEqual(layoutB.boxes);
  });

  test("layout keeps separate components spatially separate", () => {
    const graph = build(CATALOG, { "1": 1, "4": 1 }, settingsWith());
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
      { source: 1, target: 2, kind: "similarity" as const, similarity: 1, sharedFeatureCount: 1, topFactors: [] },
    ];
    const components = connectedComponents(nodes, edges);
    expect(components.map((component) => component.nodeIds)).toEqual([[1, 2], [3], [4]]);
  });
});

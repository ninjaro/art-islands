import { scoreRecommendations } from "./recommendations";
import type { TagIndex } from "./tagIndex";
import { coTaggedCandidates, similarityBetween } from "./tagIndex";
import type { CatalogItem, IslandsSettings, Ratings, Settings } from "./types";

export type IslandNodeState = "liked" | "disliked" | "recommended";

export interface IslandNode {
  id: number;
  state: IslandNodeState;
  /** Present for recommended nodes: recommendation score and evidence. */
  score?: number;
  likedSharedTags?: number;
  dislikedSharedTags?: number;
}

export type IslandEdgeKind = "similarity" | "explicit";

export interface IslandEdge {
  /** Lower entity id first; edges are undirected. */
  source: number;
  target: number;
  kind: IslandEdgeKind;
  similarity: number;
  sharedTagCount: number;
  topTags: number[];
  /** Original link kind for explicit relations. */
  linkKind?: number;
}

export interface IslandComponent {
  /** Deterministic ordinal: components sorted by size desc, then min id. */
  index: number;
  nodeIds: number[];
}

export interface IslandsGraph {
  nodes: IslandNode[];
  edges: IslandEdge[];
  components: IslandComponent[];
}

function edgeKey(a: number, b: number): string {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

/**
 * Build the Islands graph from local ratings.
 *
 * Seeds are all rated catalog works. Recommendation nodes come from the
 * existing tag-based recommendation scoring (positive evidence required,
 * dislikes subtract, volume-normalized) and exclude rated works. Edges are
 * either sufficiently strong tag similarity or explicit catalog relations
 * between displayed works. No artificial edges are added: disconnected
 * components are expected and preserved.
 */
export function buildIslandsGraph(
  catalog: CatalogItem[],
  index: TagIndex,
  ratings: Ratings,
  settings: Settings,
): IslandsGraph {
  const config: IslandsSettings = settings.islands;
  const catalogById = new Map(catalog.map((item) => [item.id, item]));

  const nodes: IslandNode[] = [];
  for (const item of catalog) {
    const rating = ratings[String(item.id)];
    if (rating === 1) nodes.push({ id: item.id, state: "liked" });
    else if (rating === -1) nodes.push({ id: item.id, state: "disliked" });
  }

  const recommendations = scoreRecommendations(catalog, ratings, {
    ...settings,
    recommendation: {
      ...settings.recommendation,
      limit: Math.max(1, Math.floor(config.maxRecommendationNodes)),
    },
  });
  for (const result of recommendations) {
    nodes.push({
      id: result.item.id,
      state: "recommended",
      score: result.score,
      likedSharedTags: result.likedSharedTags,
      dislikedSharedTags: result.dislikedSharedTags,
    });
  }

  nodes.sort((a, b) => a.id - b.id);
  const displayed = new Set(nodes.map((node) => node.id));

  // Inferred similarity edges: k-nearest-neighbor union, bounded by the
  // tag postings lists instead of an all-pairs comparison.
  const candidateEdges = new Map<string, IslandEdge>();
  for (const node of nodes) {
    const neighbors: IslandEdge[] = [];
    for (const otherId of coTaggedCandidates(index, node.id, displayed)) {
      const result = similarityBetween(index, node.id, otherId);
      if (result.similarity < config.minimumSimilarity) continue;
      const [source, target] = node.id < otherId ? [node.id, otherId] : [otherId, node.id];
      neighbors.push({
        source,
        target,
        kind: "similarity",
        similarity: result.similarity,
        sharedTagCount: result.sharedTagCount,
        topTags: result.topTags,
      });
    }
    neighbors.sort((a, b) => b.similarity - a.similarity || a.source - b.source || a.target - b.target);
    for (const edge of neighbors.slice(0, Math.max(0, Math.floor(config.maxNeighborsPerSeed)))) {
      candidateEdges.set(edgeKey(edge.source, edge.target), edge);
    }
  }

  // Explicit relations between displayed works, visually distinguishable
  // from inferred similarity. They replace an inferred edge on the same pair.
  const explicitEdges = new Map<string, IslandEdge>();
  for (const node of nodes) {
    const item = catalogById.get(node.id);
    if (!item) continue;
    for (const [targetId, linkKind] of item.links || []) {
      if (targetId === node.id || !displayed.has(targetId)) continue;
      const key = edgeKey(node.id, targetId);
      if (explicitEdges.has(key)) continue;
      const result = similarityBetween(index, node.id, targetId);
      const [source, target] = node.id < targetId ? [node.id, targetId] : [targetId, node.id];
      explicitEdges.set(key, {
        source,
        target,
        kind: "explicit",
        similarity: result.similarity,
        sharedTagCount: result.sharedTagCount,
        topTags: result.topTags,
        linkKind,
      });
    }
  }

  const maxEdges = Math.max(0, Math.floor(config.maxEdges));
  const edges: IslandEdge[] = [];
  const usedKeys = new Set<string>();
  const sortedExplicit = [...explicitEdges.values()].sort(
    (a, b) => b.similarity - a.similarity || a.source - b.source || a.target - b.target,
  );
  const sortedInferred = [...candidateEdges.values()].sort(
    (a, b) => b.similarity - a.similarity || a.source - b.source || a.target - b.target,
  );
  for (const edge of [...sortedExplicit, ...sortedInferred]) {
    if (edges.length >= maxEdges) break;
    const key = edgeKey(edge.source, edge.target);
    if (usedKeys.has(key)) continue;
    usedKeys.add(key);
    edges.push(edge);
  }
  edges.sort((a, b) => a.source - b.source || a.target - b.target);

  return { nodes, edges, components: connectedComponents(nodes, edges) };
}

/** Connected components computed from the actual displayed edges only. */
export function connectedComponents(nodes: IslandNode[], edges: IslandEdge[]): IslandComponent[] {
  const parent = new Map<number, number>();
  function find(x: number): number {
    let root = x;
    while (parent.get(root) !== root) root = parent.get(root)!;
    let current = x;
    while (parent.get(current) !== current) {
      const next = parent.get(current)!;
      parent.set(current, root);
      current = next;
    }
    return root;
  }
  for (const node of nodes) parent.set(node.id, node.id);
  for (const edge of edges) {
    const a = find(edge.source);
    const b = find(edge.target);
    if (a !== b) parent.set(Math.max(a, b), Math.min(a, b));
  }

  const groups = new Map<number, number[]>();
  for (const node of nodes) {
    const root = find(node.id);
    let group = groups.get(root);
    if (!group) {
      group = [];
      groups.set(root, group);
    }
    group.push(node.id);
  }

  return [...groups.values()]
    .map((nodeIds) => nodeIds.sort((a, b) => a - b))
    .sort((a, b) => b.length - a.length || a[0] - b[0])
    .map((nodeIds, index) => ({ index, nodeIds }));
}

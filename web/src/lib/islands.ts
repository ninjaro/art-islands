import type { DomainModel } from "./domain";
import type { EdgeFactor, FeatureIndex } from "./features";
import { similarityBetween, similarityCandidates } from "./features";
import { scoreRecommendations } from "./recommendations";
import type { IslandsSettings, Ratings, Settings } from "./types";

export type IslandNodeState = "liked" | "disliked" | "recommended";

export interface IslandNode {
  id: number;
  state: IslandNodeState;
  /** Present for recommended nodes: recommendation score and evidence. */
  score?: number;
  topFactors?: EdgeFactor[];
}

export type IslandEdgeKind = "similarity" | "explicit";

export interface IslandEdge {
  /** Lower entity id first; edges are undirected. */
  source: number;
  target: number;
  kind: IslandEdgeKind;
  similarity: number;
  sharedFeatureCount: number;
  topFactors: EdgeFactor[];
  /** Relation type code for explicit relations (e.g. "adapted_from"). */
  relationType?: string;
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
 * shared feature-based recommendation scoring (positive evidence required,
 * dislikes subtract, volume-normalized) and exclude rated works. Inferred
 * edges use a bounded up-to-K nearest-neighbor union: every node selects at
 * most maxInferredNeighborsPerNode candidates from the inverted feature
 * index (never all pairs); a node may still receive more incident edges by
 * being selected by others. Explicit catalog relations between displayed
 * works are preserved separately and never dropped for being outside the K
 * nearest. No artificial edges are added: disconnected components are
 * expected and preserved. A similarity that is not strictly positive never
 * creates an inferred edge.
 */
export function buildIslandsGraph(
  domain: DomainModel,
  index: FeatureIndex,
  ratings: Ratings,
  settings: Settings,
): IslandsGraph {
  const config: IslandsSettings = settings.islands;

  const nodes: IslandNode[] = [];
  for (const work of domain.works) {
    const rating = ratings[String(work.id)];
    if (rating === 1) nodes.push({ id: work.id, state: "liked" });
    else if (rating === -1) nodes.push({ id: work.id, state: "disliked" });
  }

  const recommendations = scoreRecommendations(domain, index, ratings, {
    ...settings,
    recommendation: {
      ...settings.recommendation,
      limit: Math.max(1, Math.floor(config.maxRecommendationNodes)),
    },
  });
  for (const result of recommendations) {
    nodes.push({
      id: result.work.id,
      state: "recommended",
      score: result.score,
      topFactors: result.positive.slice(0, 3),
    });
  }

  nodes.sort((a, b) => a.id - b.id);
  const displayed = new Set(nodes.map((node) => node.id));

  // Inferred similarity edges: up-to-K nearest-neighbor union, bounded by the
  // inverted feature index instead of an all-pairs comparison.
  const maxNeighbors = Math.max(0, Math.floor(config.maxInferredNeighborsPerNode));
  const candidateEdges = new Map<string, IslandEdge>();
  for (const node of nodes) {
    const neighbors: IslandEdge[] = [];
    for (const otherId of similarityCandidates(index, node.id, displayed)) {
      const result = similarityBetween(index, node.id, otherId);
      if (result.similarity <= 0 || result.similarity < config.minimumSimilarity) continue;
      const [source, target] = node.id < otherId ? [node.id, otherId] : [otherId, node.id];
      neighbors.push({
        source,
        target,
        kind: "similarity",
        similarity: result.similarity,
        sharedFeatureCount: result.sharedFeatureCount,
        topFactors: result.topFactors,
      });
    }
    neighbors.sort((a, b) => b.similarity - a.similarity || a.source - b.source || a.target - b.target);
    for (const edge of neighbors.slice(0, maxNeighbors)) {
      candidateEdges.set(edgeKey(edge.source, edge.target), edge);
    }
  }

  // Explicit relations between displayed works stay visually distinguishable
  // from inferred similarity. They replace an inferred edge on the same pair
  // and are never removed for being outside a node's K nearest neighbors.
  const explicitEdges = new Map<string, IslandEdge>();
  for (const relation of domain.workRelations) {
    if (relation.source === relation.target) continue;
    if (!displayed.has(relation.source) || !displayed.has(relation.target)) continue;
    const key = edgeKey(relation.source, relation.target);
    if (explicitEdges.has(key)) continue;
    const result = similarityBetween(index, relation.source, relation.target);
    const [source, target] =
      relation.source < relation.target ? [relation.source, relation.target] : [relation.target, relation.source];
    explicitEdges.set(key, {
      source,
      target,
      kind: "explicit",
      similarity: result.similarity,
      sharedFeatureCount: result.sharedFeatureCount,
      topFactors: result.topFactors,
      relationType: relation.type,
    });
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

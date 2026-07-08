import type { BroadKind, DomainModel } from "./domain";
import type { FeatureIndex } from "./features";
import { similarityBetween } from "./features";
import type { EdgeEvidence, EvolutionExport, EvolutionNode, EvolutionSettings } from "./types";

export interface EvolutionChild {
  id: number;
  /** Evidence supporting the inferred parent edge (from the build-time export). */
  evidence: EdgeEvidence;
}

export interface EvolutionForest {
  /** parentId -> children sorted by edge score desc, then id. */
  childrenByParent: Map<number, EvolutionChild[]>;
  /** Root ids ranked by subtree size desc, then id. */
  roots: number[];
  /** entityId -> subtree size (including the node itself). */
  subtreeSizes: Map<number, number>;
  /** entityId -> its lineage record. */
  byId: Map<number, EvolutionNode>;
}

/**
 * A `+N` placeholder is a UI grouping object, not an entity and not a graph
 * fact. It carries the real, explicit list of hidden child entity ids.
 */
export interface ChildPlaceholder {
  key: string;
  parentId: number;
  kind: BroadKind;
  childIds: number[];
}

export interface VisibleChildren {
  visible: EvolutionChild[];
  placeholders: ChildPlaceholder[];
}

export function buildForest(data: EvolutionExport): EvolutionForest {
  const byId = new Map<number, EvolutionNode>();
  const childrenByParent = new Map<number, EvolutionChild[]>();
  const rootIds: number[] = [];

  for (const node of data.nodes) {
    byId.set(node.id, node);
    if (node.parent === null) {
      rootIds.push(node.id);
      continue;
    }
    let children = childrenByParent.get(node.parent);
    if (!children) {
      children = [];
      childrenByParent.set(node.parent, children);
    }
    children.push({ id: node.id, evidence: node.evidence });
  }

  for (const children of childrenByParent.values()) {
    children.sort((a, b) => b.evidence.score - a.evidence.score || a.id - b.id);
  }

  // Iterative subtree sizing (the forest can be deep).
  const subtreeSizes = new Map<number, number>();
  const order: number[] = [];
  const stack = [...byId.keys()];
  const visited = new Set<number>();
  for (const start of rootIds) {
    const walk = [start];
    while (walk.length) {
      const id = walk.pop()!;
      if (visited.has(id)) continue;
      visited.add(id);
      order.push(id);
      for (const child of childrenByParent.get(id) || []) walk.push(child.id);
    }
  }
  // Defensive: include any nodes unreachable from roots (should not happen).
  for (const id of stack) {
    if (!visited.has(id)) order.push(id);
  }
  for (let i = order.length - 1; i >= 0; i -= 1) {
    const id = order[i];
    let size = 1;
    for (const child of childrenByParent.get(id) || []) {
      size += subtreeSizes.get(child.id) || 1;
    }
    subtreeSizes.set(id, size);
  }

  const roots = [...rootIds].sort(
    (a, b) => (subtreeSizes.get(b) || 1) - (subtreeSizes.get(a) || 1) || a - b,
  );

  return { childrenByParent, roots, subtreeSizes, byId };
}

/**
 * Split a parent's children into the strongest initially visible few and
 * grouped placeholders for the rest.
 *
 * Children may share a placeholder only when they have the same direct
 * parent, the same broad work kind, and a sufficiently similar feature
 * profile. Several groups produce several placeholders rather than one
 * misleading `+N` bucket.
 */
export function groupChildren(
  parentId: number,
  children: EvolutionChild[],
  domain: DomainModel,
  index: FeatureIndex,
  settings: EvolutionSettings,
  expandedGroups: ReadonlySet<string>,
): VisibleChildren {
  const visibleLimit = Math.max(0, Math.floor(settings.visibleChildrenPerNode));
  if (children.length <= visibleLimit + 1) {
    // A placeholder hiding a single child would be noise; show everything.
    return { visible: children, placeholders: [] };
  }

  const visible = children.slice(0, visibleLimit);
  const hidden = children.slice(visibleLimit);

  const placeholders: ChildPlaceholder[] = [];
  const expandedChildren: EvolutionChild[] = [];

  // Greedy deterministic grouping in score order: a hidden child joins the
  // first group whose representative shares its broad kind and whose feature
  // profile is similar enough; otherwise it starts a new group.
  interface Group {
    kind: BroadKind;
    representative: number;
    members: EvolutionChild[];
  }
  const groups: Group[] = [];
  for (const child of hidden) {
    const kind = domain.workById.get(child.id)?.broadKind ?? "work";
    let placed = false;
    for (const group of groups) {
      if (group.kind !== kind) continue;
      const { similarity } = similarityBetween(index, group.representative, child.id);
      if (similarity >= settings.groupingSimilarity) {
        group.members.push(child);
        placed = true;
        break;
      }
    }
    if (!placed) {
      groups.push({ kind, representative: child.id, members: [child] });
    }
  }

  for (const group of groups) {
    const key = `${parentId}:${group.kind}:${group.representative}`;
    if (expandedGroups.has(key)) {
      expandedChildren.push(...group.members);
    } else {
      placeholders.push({
        key,
        parentId,
        kind: group.kind,
        childIds: group.members.map((member) => member.id),
      });
    }
  }

  expandedChildren.sort((a, b) => b.evidence.score - a.evidence.score || a.id - b.id);
  return { visible: [...visible, ...expandedChildren], placeholders };
}

export interface RevealResult {
  rootId: number;
  expandNodes: number[];
  expandGroups: string[];
}

/**
 * Compute everything needed to make a work visible: the ancestor chain to
 * expand, any placeholder groups hiding it along the way, and its root.
 */
export function revealWork(
  targetId: number,
  forest: EvolutionForest,
  domain: DomainModel,
  index: FeatureIndex,
  settings: EvolutionSettings,
): RevealResult | null {
  if (!forest.byId.has(targetId)) return null;

  const path: number[] = [];
  let current: number | null = targetId;
  const guard = new Set<number>();
  while (current !== null) {
    if (guard.has(current)) return null; // defensive; export guarantees no cycles
    guard.add(current);
    path.push(current);
    const record = forest.byId.get(current);
    if (!record) return null;
    current = record.parent;
  }
  path.reverse(); // root first

  const expandNodes: number[] = [];
  const expandGroups: string[] = [];
  for (let i = 0; i + 1 < path.length; i += 1) {
    const parentId = path[i];
    const childId = path[i + 1];
    expandNodes.push(parentId);
    const children = forest.childrenByParent.get(parentId) || [];
    const { placeholders } = groupChildren(parentId, children, domain, index, settings, new Set());
    for (const placeholder of placeholders) {
      if (placeholder.childIds.includes(childId)) {
        expandGroups.push(placeholder.key);
        break;
      }
    }
  }

  return { rootId: path[0], expandNodes, expandGroups };
}

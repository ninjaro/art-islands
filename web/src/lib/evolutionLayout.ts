import { hierarchy, tree } from "d3-hierarchy";
import type { ChildPlaceholder, EvolutionChild, EvolutionForest } from "./evolution";
import { groupChildren } from "./evolution";
import type { TagIndex } from "./tagIndex";
import type { CatalogItem, EvolutionSettings } from "./types";

export interface EvolutionViewState {
  expandedNodes: ReadonlySet<number>;
  expandedGroups: ReadonlySet<string>;
  visibleRootCount: number;
  pinnedRoots: ReadonlySet<number>;
}

export interface VisibleTreeNode {
  key: string;
  type: "work" | "placeholder" | "fold";
  entityId?: number;
  placeholder?: ChildPlaceholder;
  /** Lineage edge metadata from the parent (absent for roots). */
  edge?: EvolutionChild;
  /** Total direct children in the full forest (for the expand control). */
  childCount: number;
  expanded: boolean;
  children: VisibleTreeNode[];
}

export interface PlacedNode {
  node: VisibleTreeNode;
  x: number;
  y: number;
}

export interface PlacedEdge {
  key: string;
  sourceKey: string;
  targetKey: string;
}

export interface ForestLayout {
  nodes: PlacedNode[];
  edges: PlacedEdge[];
}

export function workKey(entityId: number): string {
  return `w${entityId}`;
}

function buildVisibleTree(
  entityId: number,
  edge: EvolutionChild | undefined,
  forest: EvolutionForest,
  catalogById: Map<number, CatalogItem>,
  index: TagIndex,
  settings: EvolutionSettings,
  state: EvolutionViewState,
): VisibleTreeNode {
  const allChildren = forest.childrenByParent.get(entityId) || [];
  const expanded = state.expandedNodes.has(entityId) && allChildren.length > 0;
  const node: VisibleTreeNode = {
    key: workKey(entityId),
    type: "work",
    entityId,
    edge,
    childCount: allChildren.length,
    expanded,
    children: [],
  };
  if (!expanded) return node;

  const { visible, placeholders } = groupChildren(
    entityId,
    allChildren,
    catalogById,
    index,
    settings,
    state.expandedGroups,
  );
  for (const child of visible) {
    node.children.push(
      buildVisibleTree(child.id, child, forest, catalogById, index, settings, state),
    );
  }
  for (const placeholder of placeholders) {
    node.children.push({
      key: `p:${placeholder.key}`,
      type: "placeholder",
      placeholder,
      childCount: placeholder.childIds.length,
      expanded: false,
      children: [],
    });
  }
  // Expanded placeholder groups stay collapsible.
  for (const groupKey of collapsibleGroupKeys(entityId, allChildren, catalogById, index, settings, state)) {
    node.children.push({
      key: `f:${groupKey}`,
      type: "fold",
      placeholder: { key: groupKey, parentId: entityId, kind: "work", childIds: [] },
      childCount: 0,
      expanded: false,
      children: [],
    });
  }
  return node;
}

function collapsibleGroupKeys(
  parentId: number,
  children: EvolutionChild[],
  catalogById: Map<number, CatalogItem>,
  index: TagIndex,
  settings: EvolutionSettings,
  state: EvolutionViewState,
): string[] {
  // Re-run grouping with nothing expanded to learn all group keys, then keep
  // the ones the user expanded.
  const { placeholders } = groupChildren(
    parentId,
    children,
    catalogById,
    index,
    settings,
    new Set(),
  );
  return placeholders
    .map((placeholder) => placeholder.key)
    .filter((key) => state.expandedGroups.has(key));
}

export function visibleRootIds(forest: EvolutionForest, state: EvolutionViewState): number[] {
  const roots = forest.roots.slice(0, Math.max(0, state.visibleRootCount));
  const seen = new Set(roots);
  for (const pinned of state.pinnedRoots) {
    if (!seen.has(pinned) && forest.byId.get(pinned)?.parent === null) {
      roots.push(pinned);
      seen.add(pinned);
    }
  }
  return roots;
}

export function buildVisibleForest(
  forest: EvolutionForest,
  catalogById: Map<number, CatalogItem>,
  index: TagIndex,
  settings: EvolutionSettings,
  state: EvolutionViewState,
): VisibleTreeNode[] {
  return visibleRootIds(forest, state).map((rootId) =>
    buildVisibleTree(rootId, undefined, forest, catalogById, index, settings, state),
  );
}

const LEVEL_WIDTH = 280;
const ROW_HEIGHT = 60;
const TREE_GAP = 90;

/**
 * Deterministic horizontal tidy-tree layout: depth maps to x (time flows
 * left to right along inferred lineage), trees stack vertically.
 */
export function layoutForest(rootsVisible: VisibleTreeNode[]): ForestLayout {
  const nodes: PlacedNode[] = [];
  const edges: PlacedEdge[] = [];
  let offsetY = 0;

  for (const root of rootsVisible) {
    const rootHierarchy = hierarchy<VisibleTreeNode>(root, (node) => node.children);
    const layout = tree<VisibleTreeNode>().nodeSize([ROW_HEIGHT, LEVEL_WIDTH]);
    const placed = layout(rootHierarchy);

    let minX = Infinity;
    let maxX = -Infinity;
    placed.each((point) => {
      minX = Math.min(minX, point.x);
      maxX = Math.max(maxX, point.x);
    });
    if (!Number.isFinite(minX)) {
      minX = 0;
      maxX = 0;
    }

    placed.each((point) => {
      nodes.push({
        node: point.data,
        x: point.y,
        y: point.x - minX + offsetY,
      });
      if (point.parent) {
        edges.push({
          key: `${point.parent.data.key}->${point.data.key}`,
          sourceKey: point.parent.data.key,
          targetKey: point.data.key,
        });
      }
    });

    offsetY += maxX - minX + TREE_GAP;
  }

  return { nodes, edges };
}

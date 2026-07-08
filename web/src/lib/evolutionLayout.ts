import { hierarchy, tree } from "d3-hierarchy";
import type { DomainModel } from "./domain";
import type { ChildPlaceholder, EvolutionChild, EvolutionForest } from "./evolution";
import { groupChildren } from "./evolution";
import type { FeatureIndex } from "./features";
import type { EvolutionSettings } from "./types";

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
  domain: DomainModel,
  index: FeatureIndex,
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
    domain,
    index,
    settings,
    state.expandedGroups,
  );
  for (const child of visible) {
    node.children.push(buildVisibleTree(child.id, child, forest, domain, index, settings, state));
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
  for (const groupKey of collapsibleGroupKeys(entityId, allChildren, domain, index, settings, state)) {
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
  domain: DomainModel,
  index: FeatureIndex,
  settings: EvolutionSettings,
  state: EvolutionViewState,
): string[] {
  // Re-run grouping with nothing expanded to learn all group keys, then keep
  // the ones the user expanded.
  const { placeholders } = groupChildren(parentId, children, domain, index, settings, new Set());
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
  domain: DomainModel,
  index: FeatureIndex,
  settings: EvolutionSettings,
  state: EvolutionViewState,
): VisibleTreeNode[] {
  return visibleRootIds(forest, state).map((rootId) =>
    buildVisibleTree(rootId, undefined, forest, domain, index, settings, state),
  );
}

export const LEVEL_WIDTH = 280;
const ROW_HEIGHT = 60;
const TREE_GAP = 90;

/**
 * Deterministic layout on one shared chronological coordinate system.
 *
 * All visible dated work nodes share a single ordinal year axis: every
 * distinct year becomes a column, earlier years are always further left, and
 * the same year lands on the same x in every tree. Because a parent is
 * strictly earlier than its child, children always sit right of their
 * parents. Placeholders and undated children fall back to one column right
 * of their parent. Trees stack vertically on one canvas (d3 tidy-tree row
 * placement); undated roots form a trailing section at x = 0.
 */
export function layoutForest(
  rootsVisible: VisibleTreeNode[],
  yearOf: (entityId: number) => number | null,
): ForestLayout {
  // Pass 1: one shared, monotonic year -> column mapping across all trees.
  const years = new Set<number>();
  const collect = (node: VisibleTreeNode) => {
    if (node.type === "work" && node.entityId !== undefined) {
      const year = yearOf(node.entityId);
      if (year !== null) years.add(year);
    }
    for (const child of node.children) collect(child);
  };
  for (const root of rootsVisible) collect(root);
  const columnByYear = new Map<number, number>();
  [...years].sort((a, b) => a - b).forEach((year, column) => columnByYear.set(year, column));

  const columnOf = (node: VisibleTreeNode, parentColumn: number): number => {
    if (node.type === "work" && node.entityId !== undefined) {
      const year = yearOf(node.entityId);
      if (year !== null) {
        const column = columnByYear.get(year);
        if (column !== undefined) return column;
      }
    }
    return parentColumn + 1;
  };

  const nodes: PlacedNode[] = [];
  const edges: PlacedEdge[] = [];
  let offsetY = 0;

  const dated: VisibleTreeNode[] = [];
  const undated: VisibleTreeNode[] = [];
  for (const root of rootsVisible) {
    const isUndatedLeaf =
      root.type === "work" &&
      root.entityId !== undefined &&
      yearOf(root.entityId) === null &&
      root.children.length === 0 &&
      root.childCount === 0;
    (isUndatedLeaf ? undated : dated).push(root);
  }

  for (const root of dated) {
    const rootHierarchy = hierarchy<VisibleTreeNode>(root, (node) => node.children);
    const layout = tree<VisibleTreeNode>().nodeSize([ROW_HEIGHT, LEVEL_WIDTH]);
    const placed = layout(rootHierarchy);

    let minRow = Infinity;
    let maxRow = -Infinity;
    placed.each((point) => {
      minRow = Math.min(minRow, point.x);
      maxRow = Math.max(maxRow, point.x);
    });
    if (!Number.isFinite(minRow)) {
      minRow = 0;
      maxRow = 0;
    }

    // Resolve chronological columns top-down so fallbacks know their parent.
    const columns = new Map<VisibleTreeNode, number>();
    placed.each((point) => {
      const parentColumn = point.parent ? columns.get(point.parent.data)! : -1;
      columns.set(point.data, columnOf(point.data, parentColumn));
    });

    placed.each((point) => {
      nodes.push({
        node: point.data,
        x: columns.get(point.data)! * LEVEL_WIDTH,
        y: point.x - minRow + offsetY,
      });
      if (point.parent) {
        edges.push({
          key: `${point.parent.data.key}->${point.data.key}`,
          sourceKey: point.parent.data.key,
          targetKey: point.data.key,
        });
      }
    });

    offsetY += maxRow - minRow + TREE_GAP;
  }

  // Undated roots: a separate trailing section on the same canvas.
  for (const root of undated) {
    nodes.push({ node: root, x: 0, y: offsetY });
    offsetY += ROW_HEIGHT;
  }

  return { nodes, edges };
}

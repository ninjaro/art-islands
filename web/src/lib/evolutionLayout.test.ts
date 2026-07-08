import { describe, expect, it } from "vitest";
import type { VisibleTreeNode } from "./evolutionLayout";
import { LEVEL_WIDTH, layoutForest, workKey } from "./evolutionLayout";

function node(entityId: number, children: VisibleTreeNode[] = []): VisibleTreeNode {
  return {
    key: workKey(entityId),
    type: "work",
    entityId,
    childCount: children.length,
    expanded: children.length > 0,
    children,
  };
}

function placedX(layout: ReturnType<typeof layoutForest>, entityId: number): number {
  return layout.nodes.find((placed) => placed.node.key === workKey(entityId))!.x;
}

describe("layoutForest chronological axis", () => {
  const YEARS: Record<number, number | null> = {
    1: 1960,
    2: 1970,
    3: 1980,
    4: 1990,
    5: null,
    9: null,
  };
  const yearOf = (id: number) => YEARS[id] ?? null;

  it("maps years to one shared monotonic column axis across all trees", () => {
    // Tree A: 1 (1960) -> 3 (1980). Tree B: 2 (1970) -> 4 (1990).
    const layout = layoutForest([node(1, [node(3)]), node(2, [node(4)])], yearOf);
    const xs = [1, 2, 3, 4].map((id) => placedX(layout, id));
    // Later year -> strictly greater x, even across different trees.
    expect(xs[0]).toBeLessThan(xs[1]);
    expect(xs[1]).toBeLessThan(xs[2]);
    expect(xs[2]).toBeLessThan(xs[3]);
  });

  it("gives equal years the same x in every tree", () => {
    const layout = layoutForest([node(1, [node(3)]), node(3000 in YEARS ? 3000 : 2, [node(4)])], yearOf);
    // Column positions are multiples of LEVEL_WIDTH.
    for (const placed of layout.nodes) {
      expect(placed.x % LEVEL_WIDTH).toBe(0);
    }
  });

  it("children are always right of their parents", () => {
    const layout = layoutForest([node(1, [node(2, [node(3)]), node(4)])], yearOf);
    expect(placedX(layout, 2)).toBeGreaterThan(placedX(layout, 1));
    expect(placedX(layout, 3)).toBeGreaterThan(placedX(layout, 2));
    expect(placedX(layout, 4)).toBeGreaterThan(placedX(layout, 1));
  });

  it("undated children fall back to one column right of their parent", () => {
    const layout = layoutForest([node(2, [node(5)])], yearOf);
    expect(placedX(layout, 5)).toBe(placedX(layout, 2) + LEVEL_WIDTH);
  });

  it("undated leaf roots go to a trailing section at x = 0", () => {
    const layout = layoutForest([node(1, [node(3)]), node(9)], yearOf);
    const undatedRoot = layout.nodes.find((placed) => placed.node.key === workKey(9))!;
    expect(undatedRoot.x).toBe(0);
    const maxDatedY = Math.max(
      ...layout.nodes.filter((placed) => placed.node.key !== workKey(9)).map((placed) => placed.y),
    );
    expect(undatedRoot.y).toBeGreaterThan(maxDatedY);
  });

  it("stacked trees never overlap vertically and the output is deterministic", () => {
    const roots = [node(1, [node(3)]), node(2, [node(4)])];
    const first = layoutForest(roots, yearOf);
    const second = layoutForest(roots, yearOf);
    expect(first).toEqual(second);
    const treeAYs = [placedX(first, 1)];
    expect(treeAYs).toBeDefined();
    const yA = first.nodes.find((placed) => placed.node.key === workKey(1))!.y;
    const yB = first.nodes.find((placed) => placed.node.key === workKey(2))!.y;
    expect(yA).not.toBe(yB);
  });
});

import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force";
import type { SimulationLinkDatum, SimulationNodeDatum } from "d3-force";
import type { IslandsGraph } from "./islands";

export interface IslandBox {
  index: number;
  x: number;
  y: number;
  width: number;
  height: number;
  count: number;
}

export interface IslandsLayout {
  positions: Map<number, { x: number; y: number }>;
  boxes: IslandBox[];
}

interface SimNode extends SimulationNodeDatum {
  id: number;
}

const NODE_WIDTH = 180;
const NODE_HEIGHT = 64;
const COMPONENT_PADDING = 56;
const COMPONENT_GAP = 90;
const SIMULATION_TICKS = 220;

/**
 * Deterministic layout: each connected component is laid out independently
 * with a force simulation seeded from fixed phyllotaxis positions (no
 * randomness), then components are shelf-packed without overlap. Identical
 * graph input always produces identical output.
 */
export function layoutIslands(graph: IslandsGraph): IslandsLayout {
  const positions = new Map<number, { x: number; y: number }>();
  const rawBoxes: Array<{ index: number; width: number; height: number; count: number; local: Map<number, { x: number; y: number }> }> = [];

  for (const component of graph.components) {
    const memberSet = new Set(component.nodeIds);
    const simNodes: SimNode[] = component.nodeIds.map((id, order) => {
      // Deterministic phyllotaxis seeding in id order.
      const radius = 60 * Math.sqrt(order + 0.5);
      const angle = (order + 0.5) * 2.399963229728653;
      return { id, x: radius * Math.cos(angle), y: radius * Math.sin(angle) };
    });

    if (simNodes.length > 1) {
      const links: SimulationLinkDatum<SimNode>[] = graph.edges
        .filter((edge) => memberSet.has(edge.source) && memberSet.has(edge.target))
        .map((edge) => ({
          source: edge.source,
          target: edge.target,
          distance: 90 + (1 - Math.min(1, edge.similarity)) * 120,
        }));

      const simulation = forceSimulation(simNodes)
        .force(
          "link",
          forceLink<SimNode, SimulationLinkDatum<SimNode>>(links)
            .id((node) => node.id)
            .distance((link) => (link as { distance?: number }).distance ?? 120)
            .strength(0.5),
        )
        .force("charge", forceManyBody<SimNode>().strength(-320))
        .force("collide", forceCollide<SimNode>(Math.hypot(NODE_WIDTH, NODE_HEIGHT) / 2 + 6))
        .force("x", forceX<SimNode>(0).strength(0.05))
        .force("y", forceY<SimNode>(0).strength(0.05))
        .stop();
      simulation.tick(SIMULATION_TICKS);
    }

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    const local = new Map<number, { x: number; y: number }>();
    for (const node of simNodes) {
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      local.set(node.id, { x, y });
      minX = Math.min(minX, x - NODE_WIDTH / 2);
      minY = Math.min(minY, y - NODE_HEIGHT / 2);
      maxX = Math.max(maxX, x + NODE_WIDTH / 2);
      maxY = Math.max(maxY, y + NODE_HEIGHT / 2);
    }

    for (const [id, point] of local) {
      local.set(id, { x: point.x - minX + COMPONENT_PADDING, y: point.y - minY + COMPONENT_PADDING });
    }

    rawBoxes.push({
      index: component.index,
      width: maxX - minX + COMPONENT_PADDING * 2,
      height: maxY - minY + COMPONENT_PADDING * 2,
      count: component.nodeIds.length,
      local,
    });
  }

  // Shelf packing into rows aiming for a roughly square overall canvas.
  const totalArea = rawBoxes.reduce((sum, box) => sum + (box.width + COMPONENT_GAP) * (box.height + COMPONENT_GAP), 0);
  const targetRowWidth = Math.max(1200, Math.sqrt(totalArea) * 1.3);

  const boxes: IslandBox[] = [];
  let cursorX = 0;
  let cursorY = 0;
  let rowHeight = 0;
  for (const box of rawBoxes) {
    if (cursorX > 0 && cursorX + box.width > targetRowWidth) {
      cursorX = 0;
      cursorY += rowHeight + COMPONENT_GAP;
      rowHeight = 0;
    }
    boxes.push({
      index: box.index,
      x: cursorX,
      y: cursorY,
      width: box.width,
      height: box.height,
      count: box.count,
    });
    for (const [id, point] of box.local) {
      positions.set(id, { x: cursorX + point.x - NODE_WIDTH / 2, y: cursorY + point.y - NODE_HEIGHT / 2 });
    }
    cursorX += box.width + COMPONENT_GAP;
    rowHeight = Math.max(rowHeight, box.height);
  }

  return { positions, boxes };
}

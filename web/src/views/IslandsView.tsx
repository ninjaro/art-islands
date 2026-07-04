import { useCallback, useDeferredValue, useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import type { Edge, Node, NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { buildIslandsGraph } from "../lib/islands";
import type { IslandNode, IslandsGraph } from "../lib/islands";
import { layoutIslands } from "../lib/islandsLayout";
import { yearLabel } from "../lib/format";
import type { TagIndex } from "../lib/tagIndex";
import type { AppData, CatalogItem, Ratings, Settings } from "../lib/types";
import type { OpenHandler, RateHandler } from "../components/common";
import { SvgIcon, kindIconName } from "../components/icons";

interface IslandNodeData extends Record<string, unknown> {
  island: IslandNode;
  item: CatalogItem;
  rating: number;
  onRate: RateHandler;
  explanationText: string;
}

type IslandFlowNode = Node<IslandNodeData>;

interface IslandBgData extends Record<string, unknown> {
  label: string;
  width: number;
  height: number;
  componentIndex: number;
  onFocusComponent: (index: number) => void;
}

type IslandBgFlowNode = Node<IslandBgData>;

const STATE_LABELS = { liked: "liked", disliked: "disliked", recommended: "recommended" } as const;

function WorkNode({ data }: NodeProps<IslandFlowNode>) {
  const { island, item, rating, onRate, explanationText } = data;
  const year = yearLabel(item.date);
  return (
    <div
      className={`island-node ${island.state}`}
      title={explanationText}
      aria-label={`${item.label}${year ? `, ${year}` : ""}, ${STATE_LABELS[island.state]}`}
    >
      <Handle type="target" position={Position.Left} className="hidden-handle" isConnectable={false} />
      <Handle type="source" position={Position.Right} className="hidden-handle" isConnectable={false} />
      <span className={`island-state ${island.state}`} aria-hidden="true">
        {island.state === "liked" ? (
          <SvgIcon name="like" title="" size={12} />
        ) : island.state === "disliked" ? (
          <SvgIcon name="dislike" title="" size={12} />
        ) : (
          "?"
        )}
      </span>
      <span className="island-kind">
        <SvgIcon name={kindIconName(item.kind)} title="" size={14} />
      </span>
      <span className="island-body">
        <span className="island-label">{item.label}</span>
        <span className="island-year">{year || "undated"}</span>
      </span>
      <span className="island-actions nodrag">
        <button
          type="button"
          className={rating === 1 ? "island-rate like active" : "island-rate like"}
          onClick={(event) => {
            event.stopPropagation();
            onRate(item.id, 1);
          }}
          aria-label={`Like ${item.label}`}
          aria-pressed={rating === 1}
        >
          <SvgIcon name="like" title={`Like ${item.label}`} size={13} />
        </button>
        <button
          type="button"
          className={rating === -1 ? "island-rate dislike active" : "island-rate dislike"}
          onClick={(event) => {
            event.stopPropagation();
            onRate(item.id, -1);
          }}
          aria-label={`Dislike ${item.label}`}
          aria-pressed={rating === -1}
        >
          <SvgIcon name="dislike" title={`Dislike ${item.label}`} size={13} />
        </button>
      </span>
    </div>
  );
}

function IslandBackground({ data }: NodeProps<IslandBgFlowNode>) {
  return (
    <div
      className="island-bg"
      style={{ width: data.width, height: data.height }}
      onClick={() => data.onFocusComponent(data.componentIndex)}
    >
      <button
        type="button"
        className="island-heading nodrag"
        onClick={(event) => {
          event.stopPropagation();
          data.onFocusComponent(data.componentIndex);
        }}
        aria-label={`Focus ${data.label}`}
      >
        {data.label}
      </button>
    </div>
  );
}

const nodeTypes = { islandWork: WorkNode, islandBg: IslandBackground };

function explanationFor(node: IslandNode, item: CatalogItem, graph: IslandsGraph, data: AppData): string {
  if (node.state === "liked") return `${item.label}: you liked this work.`;
  if (node.state === "disliked") return `${item.label}: you disliked this work.`;
  const parts = [`Recommended, score ${node.score?.toFixed(2)}`];
  if (node.likedSharedTags) parts.push(`${node.likedSharedTags} tags shared with liked works`);
  if (node.dislikedSharedTags) parts.push(`${node.dislikedSharedTags} tags shared with disliked works`);
  const strongestEdge = graph.edges
    .filter((edge) => edge.source === node.id || edge.target === node.id)
    .sort((a, b) => b.similarity - a.similarity)[0];
  if (strongestEdge && strongestEdge.topTags.length) {
    const names = strongestEdge.topTags.map((id) => data.tagById.get(id)?.name || `#${id}`).join(", ");
    parts.push(`strongest shared tags: ${names}`);
  }
  return parts.join("; ");
}

function IslandsCanvas({
  data,
  tagIndex,
  ratings,
  settings,
  onOpen,
  onRate,
}: {
  data: AppData;
  tagIndex: TagIndex;
  ratings: Ratings;
  settings: Settings;
  onOpen: OpenHandler;
  onRate: RateHandler;
}) {
  const { fitView } = useReactFlow();

  // Deferred ratings keep like/dislike clicks responsive; the graph and
  // layout recompute right after and stale computations are simply unused.
  const deferredRatings = useDeferredValue(ratings);

  const graph = useMemo(
    () => buildIslandsGraph(data.catalog, tagIndex, deferredRatings, settings),
    [data.catalog, tagIndex, deferredRatings, settings],
  );

  const layout = useMemo(() => layoutIslands(graph), [graph]);

  const onFocusComponent = useCallback(
    (index: number) => {
      const component = graph.components.find((candidate) => candidate.index === index);
      if (!component) return;
      fitView({
        nodes: component.nodeIds.map((id) => ({ id: `n${id}` })),
        duration: 300,
        padding: 0.25,
      });
    },
    [graph, fitView],
  );

  const nodes: Array<IslandFlowNode | IslandBgFlowNode> = useMemo(() => {
    const bgNodes: IslandBgFlowNode[] = layout.boxes.map((box) => ({
      id: `island-${box.index}`,
      type: "islandBg",
      position: { x: box.x, y: box.y },
      draggable: false,
      selectable: false,
      focusable: false,
      zIndex: -1,
      data: {
        label: `Island ${box.index + 1} · ${box.count} ${box.count === 1 ? "work" : "works"}`,
        width: box.width,
        height: box.height,
        componentIndex: box.index,
        onFocusComponent,
      },
    }));

    const workNodes: IslandFlowNode[] = graph.nodes.map((node) => {
      const item = data.catalogById.get(node.id)!;
      const position = layout.positions.get(node.id) || { x: 0, y: 0 };
      return {
        id: `n${node.id}`,
        type: "islandWork",
        position,
        data: {
          island: node,
          item,
          rating: ratings[String(node.id)] || 0,
          onRate,
          explanationText: explanationFor(node, item, graph, data),
        },
      };
    });

    return [...bgNodes, ...workNodes];
  }, [graph, layout, data, ratings, onRate, onFocusComponent]);

  const edges: Edge[] = useMemo(
    () =>
      graph.edges.map((edge) => ({
        id: `e${edge.source}-${edge.target}`,
        source: `n${edge.source}`,
        target: `n${edge.target}`,
        type: "straight",
        className: edge.kind === "explicit" ? "island-edge-explicit" : "island-edge-inferred",
        focusable: false,
      })),
    [graph],
  );

  const seedCount = graph.nodes.filter((node) => node.state !== "recommended").length;
  const recommendedCount = graph.nodes.length - seedCount;

  return (
    <div className="graph-view" data-testid="islands-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.03}
        nodesConnectable={false}
        edgesFocusable={false}
        onNodeClick={(_, node) => {
          if (node.type === "islandWork") onOpen((node.data as IslandNodeData).item.id);
        }}
      >
        <Background />
        <Controls showInteractive={false} />
        <Panel position="top-left" className="graph-panel">
          <div className="island-legend" aria-label="Legend">
            <span className="legend-item">
              <span className="legend-swatch liked" /> liked
            </span>
            <span className="legend-item">
              <span className="legend-swatch disliked" /> disliked
            </span>
            <span className="legend-item">
              <span className="legend-swatch recommended" /> recommended
            </span>
            <span className="legend-item">
              <span className="legend-line explicit" /> explicit relation
            </span>
            <span className="legend-item">
              <span className="legend-line inferred" /> inferred similarity
            </span>
          </div>
          <div className="graph-toolbar">
            <button type="button" onClick={() => fitView({ duration: 300 })}>
              Fit all
            </button>
            <span className="island-stats">
              {graph.components.length} island{graph.components.length === 1 ? "" : "s"} · {seedCount} rated ·{" "}
              {recommendedCount} recommended
            </span>
          </div>
        </Panel>
      </ReactFlow>
    </div>
  );
}

export function IslandsView({
  data,
  tagIndex,
  ratings,
  settings,
  onOpen,
  onRate,
}: {
  data: AppData;
  tagIndex: TagIndex;
  ratings: Ratings;
  settings: Settings;
  onOpen: OpenHandler;
  onRate: RateHandler;
}) {
  if (!Object.keys(ratings).length) {
    return (
      <section className="empty">
        Rate some works in Browse or Recommendations first: your liked and disliked works become the seeds of
        your islands.
      </section>
    );
  }
  return (
    <ReactFlowProvider>
      <IslandsCanvas
        data={data}
        tagIndex={tagIndex}
        ratings={ratings}
        settings={settings}
        onOpen={onOpen}
        onRate={onRate}
      />
    </ReactFlowProvider>
  );
}

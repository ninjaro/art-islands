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
import type { DomainModel, WorkViewModel } from "../lib/domain";
import { roleLabel } from "../lib/domain";
import type { FeatureIndex } from "../lib/features";
import { factorPhrase } from "../lib/features";
import { motionDuration } from "../lib/format";
import { buildIslandsGraph } from "../lib/islands";
import type { IslandEdge, IslandNode } from "../lib/islands";
import { layoutIslands } from "../lib/islandsLayout";
import type { Ratings, Settings } from "../lib/types";
import type { OpenHandler, RateHandler } from "../components/common";
import { SvgIcon, iconForBroadKind } from "../components/icons";

interface IslandNodeData extends Record<string, unknown> {
  island: IslandNode;
  work: WorkViewModel;
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
  const { island, work, rating, onRate, explanationText } = data;
  const year = work.year !== null ? String(work.year) : "";
  return (
    <div
      className={`island-node ${island.state}`}
      title={explanationText}
      aria-label={`${work.label}${year ? `, ${year}` : ""}, ${STATE_LABELS[island.state]}. ${explanationText}`}
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
        <SvgIcon name={iconForBroadKind(work.broadKind)} title="" size={14} />
      </span>
      <span className="island-body">
        <span className="island-label">{work.label}</span>
        <span className="island-year">{year || "undated"}</span>
      </span>
      <span className="island-actions nodrag">
        <button
          type="button"
          className={rating === 1 ? "island-rate like active" : "island-rate like"}
          onClick={(event) => {
            event.stopPropagation();
            onRate(work.id, 1);
          }}
          aria-label={`Like ${work.label}`}
          aria-pressed={rating === 1}
        >
          <SvgIcon name="like" title={`Like ${work.label}`} size={13} />
        </button>
        <button
          type="button"
          className={rating === -1 ? "island-rate dislike active" : "island-rate dislike"}
          onClick={(event) => {
            event.stopPropagation();
            onRate(work.id, -1);
          }}
          aria-label={`Dislike ${work.label}`}
          aria-pressed={rating === -1}
        >
          <SvgIcon name="dislike" title={`Dislike ${work.label}`} size={13} />
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

function explanationFor(node: IslandNode, work: WorkViewModel): string {
  if (node.state === "liked") return `${work.label}: you liked this work.`;
  if (node.state === "disliked") return `${work.label}: you disliked this work.`;
  const parts = [`Recommended, score ${node.score?.toFixed(2)}`];
  for (const factor of node.topFactors ?? []) {
    parts.push(factorPhrase(factor));
  }
  return parts.join("; ");
}

function edgeAriaLabel(edge: IslandEdge, domain: DomainModel): string {
  const source = domain.workById.get(edge.source)?.label ?? `#${edge.source}`;
  const target = domain.workById.get(edge.target)?.label ?? `#${edge.target}`;
  if (edge.kind === "explicit") {
    return `${source} and ${target}: ${roleLabel(edge.relationType ?? "related")} relation`;
  }
  const factors = edge.topFactors.map((factor) => factor.label).join(", ");
  return `${source} and ${target}: similarity ${edge.similarity.toFixed(2)}${factors ? `, ${factors}` : ""}`;
}

function IslandsCanvas({
  domain,
  index,
  ratings,
  settings,
  onOpen,
  onRate,
}: {
  domain: DomainModel;
  index: FeatureIndex;
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
    () => buildIslandsGraph(domain, index, deferredRatings, settings),
    [domain, index, deferredRatings, settings],
  );

  const layout = useMemo(() => layoutIslands(graph), [graph]);

  const onFocusComponent = useCallback(
    (componentIndex: number) => {
      const component = graph.components.find((candidate) => candidate.index === componentIndex);
      if (!component) return;
      fitView({
        nodes: component.nodeIds.map((id) => ({ id: `n${id}` })),
        duration: motionDuration(300),
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
      const work = domain.workById.get(node.id)!;
      const position = layout.positions.get(node.id) || { x: 0, y: 0 };
      return {
        id: `n${node.id}`,
        type: "islandWork",
        position,
        data: {
          island: node,
          work,
          rating: ratings[String(node.id)] || 0,
          onRate,
          explanationText: explanationFor(node, work),
        },
      };
    });

    return [...bgNodes, ...workNodes];
  }, [graph, layout, domain, ratings, onRate, onFocusComponent]);

  const edges: Edge[] = useMemo(
    () =>
      graph.edges.map((edge) => ({
        id: `e${edge.source}-${edge.target}`,
        source: `n${edge.source}`,
        target: `n${edge.target}`,
        type: "straight",
        className: edge.kind === "explicit" ? "island-edge-explicit" : "island-edge-inferred",
        focusable: true,
        ariaLabel: edgeAriaLabel(edge, domain),
      })),
    [graph, domain],
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
        onNodeClick={(_, node) => {
          if (node.type === "islandWork") onOpen((node.data as IslandNodeData).work.id);
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
            <button type="button" onClick={() => fitView({ duration: motionDuration(300) })}>
              Fit all
            </button>
            <span className="island-stats">
              {graph.components.length} island{graph.components.length === 1 ? "" : "s"} · {seedCount} rated ·{" "}
              {recommendedCount} recommended
            </span>
          </div>
          <p className="graph-help">
            Each work connects to at most {settings.islands.maxInferredNeighborsPerNode} nearest neighbors with
            similarity ≥ {settings.islands.minimumSimilarity}. Solid edges are explicit catalog relations; dashed
            edges are inferred similarity. Hover or focus a node or edge for its evidence.
          </p>
        </Panel>
      </ReactFlow>
    </div>
  );
}

export function IslandsView({
  domain,
  index,
  ratings,
  settings,
  onOpen,
  onRate,
}: {
  domain: DomainModel;
  index: FeatureIndex;
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
        domain={domain}
        index={index}
        ratings={ratings}
        settings={settings}
        onOpen={onOpen}
        onRate={onRate}
      />
    </ReactFlowProvider>
  );
}

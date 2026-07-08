import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getSmoothStepPath,
  useReactFlow,
  useViewport,
} from "@xyflow/react";
import type { Edge, EdgeProps, Node, NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { DomainModel, WorkViewModel } from "../lib/domain";
import { buildForest, revealWork } from "../lib/evolution";
import type { EvolutionForest } from "../lib/evolution";
import { buildVisibleForest, layoutForest, workKey } from "../lib/evolutionLayout";
import type { EvolutionViewState, VisibleTreeNode } from "../lib/evolutionLayout";
import type { FeatureIndex } from "../lib/features";
import { factorPhrase } from "../lib/features";
import { motionDuration } from "../lib/format";
import type { AppData, EdgeEvidence, EvolutionSettings, Settings } from "../lib/types";
import type { OpenHandler } from "../components/common";
import { SvgIcon, iconForBroadKind } from "../components/icons";

const SESSION_KEY = "art-islands-evolution-view-v2";

interface StoredViewState {
  expandedNodes: number[];
  expandedGroups: string[];
  visibleRootCount: number;
  pinnedRoots: number[];
}

function loadStoredState(defaultRoots: number): {
  expandedNodes: Set<number>;
  expandedGroups: Set<string>;
  visibleRootCount: number;
  pinnedRoots: Set<number>;
} {
  try {
    const raw = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null") as StoredViewState | null;
    if (raw && typeof raw === "object") {
      return {
        expandedNodes: new Set(raw.expandedNodes || []),
        expandedGroups: new Set(raw.expandedGroups || []),
        visibleRootCount: raw.visibleRootCount || defaultRoots,
        pinnedRoots: new Set(raw.pinnedRoots || []),
      };
    }
  } catch {
    // fall through to defaults
  }
  return {
    expandedNodes: new Set(),
    expandedGroups: new Set(),
    visibleRootCount: defaultRoots,
    pinnedRoots: new Set(),
  };
}

interface WorkNodeData extends Record<string, unknown> {
  tree: VisibleTreeNode;
  work?: WorkViewModel;
  onOpen: OpenHandler;
  onToggle: (entityId: number) => void;
  onExpandGroup: (key: string) => void;
  onCollapseGroup: (key: string) => void;
}

type EvolutionFlowNode = Node<WorkNodeData>;

function WorkNode({ data }: NodeProps<EvolutionFlowNode>) {
  const { tree, work, onOpen, onToggle } = data;
  if (!work || tree.entityId === undefined) return null;
  const year = work.year !== null ? String(work.year) : "";
  const evidence = tree.edge?.evidence;
  const explanationText = evidence
    ? `Inferred from feature similarity ${evidence.score.toFixed(2)}, ${evidence.sharedFeatureCount} shared features` +
      (evidence.topFactors.length ? `; ${evidence.topFactors.map(factorPhrase).join("; ")}` : "")
    : "Root of an inferred branch";
  return (
    <div className="evo-node" title={explanationText}>
      <Handle type="target" position={Position.Left} className="hidden-handle" isConnectable={false} />
      <Handle type="source" position={Position.Right} className="hidden-handle" isConnectable={false} />
      <button
        type="button"
        className="evo-open"
        onClick={() => onOpen(work.id)}
        aria-label={`Open details for ${work.label}${year ? `, ${year}` : ""}`}
      >
        <span className="evo-kind">
          <SvgIcon name={iconForBroadKind(work.broadKind)} title="" size={14} />
        </span>
        <span className="evo-label">{work.label}</span>
        <span className="evo-year">{year || "—"}</span>
      </button>
      {tree.childCount > 0 ? (
        <button
          type="button"
          className="evo-toggle"
          onClick={(event) => {
            event.stopPropagation();
            onToggle(work.id);
          }}
          aria-label={
            tree.expanded
              ? `Collapse ${tree.childCount} related later works`
              : `Expand ${tree.childCount} related later works`
          }
          aria-expanded={tree.expanded}
        >
          {tree.expanded ? "−" : `▸ ${tree.childCount}`}
        </button>
      ) : null}
    </div>
  );
}

function PlaceholderNode({ data }: NodeProps<EvolutionFlowNode>) {
  const { tree, onExpandGroup, onCollapseGroup } = data;
  if (tree.type === "fold") {
    return (
      <button
        type="button"
        className="evo-node evo-placeholder evo-fold"
        onClick={() => onCollapseGroup(tree.placeholder!.key)}
        aria-label="Collapse this group of related works"
      >
        <Handle type="target" position={Position.Left} className="hidden-handle" isConnectable={false} />
        fold
      </button>
    );
  }
  const placeholder = tree.placeholder!;
  return (
    <button
      type="button"
      className="evo-node evo-placeholder"
      onClick={() => onExpandGroup(placeholder.key)}
      aria-label={`Show ${placeholder.childIds.length} more related ${placeholder.kind} works`}
      title={`${placeholder.childIds.length} hidden related works of the same kind and similar profile`}
    >
      <Handle type="target" position={Position.Left} className="hidden-handle" isConnectable={false} />
      +{placeholder.childIds.length}
    </button>
  );
}

const nodeTypes = { work: WorkNode, placeholder: PlaceholderNode };

interface EvidenceEdgeData extends Record<string, unknown> {
  evidence: EdgeEvidence;
  earlierLabel: string;
  laterLabel: string;
}

/**
 * Edge with attached evidence: a compact strongest-factor label on the edge
 * itself, and a full tooltip reachable by mouse hover AND keyboard focus.
 */
function EvidenceEdge(props: EdgeProps) {
  const [open, setOpen] = useState(false);
  const data = props.data as EvidenceEdgeData;
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  });
  const strongest = data.evidence.topFactors[0];
  return (
    <>
      <BaseEdge id={props.id} path={path} markerEnd={props.markerEnd} />
      {/* Invisible fat path as the hover/focus target. */}
      <path
        d={path}
        className="edge-hit"
        tabIndex={0}
        role="img"
        aria-label={`${data.earlierLabel} to ${data.laterLabel}: similarity ${data.evidence.score.toFixed(2)}, ${
          data.evidence.sharedFeatureCount
        } shared features`}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      />
      <EdgeLabelRenderer>
        <div
          className="edge-label nodrag nopan"
          style={{ transform: `translate(-50%,-50%) translate(${labelX}px,${labelY}px)` }}
        >
          {strongest ? <span className="edge-label-chip">{strongest.label}</span> : null}
          {open ? (
            <div className="edge-tooltip" role="tooltip">
              <strong>
                {data.earlierLabel} → {data.laterLabel}
              </strong>
              <div>
                Similarity: {data.evidence.score.toFixed(2)} · {data.evidence.sharedFeatureCount} shared features
              </div>
              {data.evidence.topFactors.length ? (
                <ul>
                  {data.evidence.topFactors.map((factor) => (
                    <li key={factor.id}>{factorPhrase(factor)}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const edgeTypes = { evidence: EvidenceEdge };

function EvolutionCanvas({
  domain,
  index,
  settings,
  forest,
  onOpen,
}: {
  domain: DomainModel;
  index: FeatureIndex;
  settings: Settings;
  forest: EvolutionForest;
  onOpen: OpenHandler;
}) {
  const evolutionSettings: EvolutionSettings = settings.evolution;
  const [state, setState] = useState(() => loadStoredState(evolutionSettings.maxInitialRoots));
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const { fitView, setCenter, setViewport } = useReactFlow();
  const { zoom } = useViewport();
  const focusTarget = useRef<number | null>(null);

  useEffect(() => {
    const stored: StoredViewState = {
      expandedNodes: [...state.expandedNodes],
      expandedGroups: [...state.expandedGroups],
      visibleRootCount: state.visibleRootCount,
      pinnedRoots: [...state.pinnedRoots],
    };
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(stored));
  }, [state]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 150);
    return () => window.clearTimeout(timer);
  }, [search]);

  const viewState: EvolutionViewState = state;

  const layout = useMemo(() => {
    const visibleForest = buildVisibleForest(forest, domain, index, evolutionSettings, viewState);
    return layoutForest(visibleForest, (entityId) => domain.workById.get(entityId)?.year ?? null);
  }, [forest, domain, index, evolutionSettings, viewState]);

  const onToggle = useCallback((entityId: number) => {
    setState((current) => {
      const expandedNodes = new Set(current.expandedNodes);
      if (expandedNodes.has(entityId)) expandedNodes.delete(entityId);
      else expandedNodes.add(entityId);
      return { ...current, expandedNodes };
    });
  }, []);

  const onExpandGroup = useCallback((key: string) => {
    setState((current) => {
      const expandedGroups = new Set(current.expandedGroups);
      expandedGroups.add(key);
      return { ...current, expandedGroups };
    });
  }, []);

  const onCollapseGroup = useCallback((key: string) => {
    setState((current) => {
      const expandedGroups = new Set(current.expandedGroups);
      expandedGroups.delete(key);
      return { ...current, expandedGroups };
    });
  }, []);

  const nodes: EvolutionFlowNode[] = useMemo(
    () =>
      layout.nodes.map((placed) => ({
        id: placed.node.key,
        type: placed.node.type === "work" ? "work" : "placeholder",
        position: { x: placed.x, y: placed.y },
        draggable: false,
        connectable: false,
        data: {
          tree: placed.node,
          work: placed.node.entityId !== undefined ? domain.workById.get(placed.node.entityId) : undefined,
          onOpen,
          onToggle,
          onExpandGroup,
          onCollapseGroup,
        },
      })),
    [layout, domain, onOpen, onToggle, onExpandGroup, onCollapseGroup],
  );

  const nodeByKey = useMemo(() => new Map(layout.nodes.map((placed) => [placed.node.key, placed.node])), [layout]);

  const edges: Edge[] = useMemo(
    () =>
      layout.edges.map((edge) => {
        const targetNode = nodeByKey.get(edge.targetKey);
        const evidence = targetNode?.type === "work" ? targetNode.edge?.evidence : undefined;
        if (!evidence) {
          // Edges into placeholders/folds carry no evidence.
          return {
            id: edge.key,
            source: edge.sourceKey,
            target: edge.targetKey,
            type: "smoothstep",
            focusable: false,
          };
        }
        const sourceNode = nodeByKey.get(edge.sourceKey);
        const earlierLabel =
          sourceNode?.entityId !== undefined ? domain.workById.get(sourceNode.entityId)?.label ?? "" : "";
        const laterLabel =
          targetNode?.entityId !== undefined ? domain.workById.get(targetNode.entityId)?.label ?? "" : "";
        return {
          id: edge.key,
          source: edge.sourceKey,
          target: edge.targetKey,
          type: "evidence",
          focusable: false,
          markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
          data: { evidence, earlierLabel, laterLabel } satisfies EvidenceEdgeData,
        };
      }),
    [layout, nodeByKey, domain],
  );

  // Focus a node after a search reveal once the new layout is in place.
  useEffect(() => {
    if (focusTarget.current === null) return;
    const key = workKey(focusTarget.current);
    const placed = layout.nodes.find((candidate) => candidate.node.key === key);
    if (placed) {
      setCenter(placed.x + 110, placed.y + 20, { zoom: 1, duration: motionDuration(300) });
      focusTarget.current = null;
    }
  }, [layout, setCenter]);

  const searchMatches = useMemo(() => {
    const query = debouncedSearch.trim().toLowerCase();
    if (query.length < 2) return [];
    const matches: WorkViewModel[] = [];
    for (const work of domain.works) {
      if (work.label.toLowerCase().includes(query)) {
        matches.push(work);
        if (matches.length >= 8) break;
      }
    }
    return matches;
  }, [debouncedSearch, domain.works]);

  function focusWork(id: number) {
    const reveal = revealWork(id, forest, domain, index, evolutionSettings);
    if (!reveal) return;
    setState((current) => {
      const expandedNodes = new Set(current.expandedNodes);
      for (const nodeId of reveal.expandNodes) expandedNodes.add(nodeId);
      const expandedGroups = new Set(current.expandedGroups);
      for (const key of reveal.expandGroups) expandedGroups.add(key);
      const pinnedRoots = new Set(current.pinnedRoots);
      pinnedRoots.add(reveal.rootId);
      return { ...current, expandedNodes, expandedGroups, pinnedRoots };
    });
    focusTarget.current = id;
    setSearch("");
  }

  function resetView() {
    setState({
      expandedNodes: new Set(),
      expandedGroups: new Set(),
      visibleRootCount: evolutionSettings.maxInitialRoots,
      pinnedRoots: new Set(),
    });
    setViewport({ x: 0, y: 0, zoom: 1 });
  }

  const totalRoots = forest.roots.length;

  return (
    <div className="graph-view" data-testid="evolution-canvas" data-zoom-low={zoom < 0.7}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        minZoom={0.05}
        nodesDraggable={false}
        nodesConnectable={false}
        proOptions={{ hideAttribution: false }}
      >
        <Background />
        <Controls showInteractive={false} />
        <Panel position="top-left" className="graph-panel">
          <p className="graph-disclaimer">
            Branches are inferred from date and feature similarity — arrows point from the earlier work to the
            later one. They do not prove direct historical influence.
          </p>
          <div className="graph-toolbar">
            <div className="graph-search">
              <input
                type="search"
                placeholder="Search work label"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                aria-label="Search work label"
              />
              {searchMatches.length ? (
                <ul className="graph-search-results" role="listbox" aria-label="Matching works">
                  {searchMatches.map((work) => (
                    <li key={work.id}>
                      <button type="button" onClick={() => focusWork(work.id)}>
                        {work.label} {work.year !== null ? `(${work.year})` : ""}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <button type="button" onClick={() => fitView({ duration: motionDuration(300) })}>
              Fit
            </button>
            <button type="button" onClick={resetView}>
              Reset view
            </button>
            {state.visibleRootCount < totalRoots ? (
              <button
                type="button"
                onClick={() =>
                  setState((current) => ({
                    ...current,
                    visibleRootCount: Math.min(
                      totalRoots,
                      current.visibleRootCount + evolutionSettings.maxInitialRoots,
                    ),
                  }))
                }
              >
                More roots ({Math.min(state.visibleRootCount, totalRoots)}/{totalRoots})
              </button>
            ) : null}
          </div>
        </Panel>
      </ReactFlow>
    </div>
  );
}

export function EvolutionView({
  data,
  domain,
  index,
  settings,
  onOpen,
}: {
  data: AppData;
  domain: DomainModel;
  index: FeatureIndex;
  settings: Settings;
  onOpen: OpenHandler;
}) {
  const forest = useMemo(() => (data.evolution ? buildForest(data.evolution) : null), [data.evolution]);

  if (!data.evolution || !forest) {
    return (
      <section className="empty">
        Evolution data is not available or outdated. Regenerate the static exports with{" "}
        <code>.venv/bin/art-islands export</code>.
      </section>
    );
  }

  return (
    <ReactFlowProvider>
      <EvolutionCanvas domain={domain} index={index} settings={settings} forest={forest} onOpen={onOpen} />
    </ReactFlowProvider>
  );
}

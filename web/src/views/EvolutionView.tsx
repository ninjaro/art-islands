import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { buildForest, revealWork } from "../lib/evolution";
import type { EvolutionForest } from "../lib/evolution";
import { buildVisibleForest, layoutForest, workKey } from "../lib/evolutionLayout";
import type { EvolutionViewState, VisibleTreeNode } from "../lib/evolutionLayout";
import { yearLabel } from "../lib/format";
import type { TagIndex } from "../lib/tagIndex";
import type { AppData, CatalogItem, EvolutionSettings, Settings } from "../lib/types";
import type { OpenHandler } from "../components/common";
import { SvgIcon, kindIconName } from "../components/icons";

const SESSION_KEY = "art-islands-evolution-view-v1";

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
  item?: CatalogItem;
  onOpen: OpenHandler;
  onToggle: (entityId: number) => void;
  onExpandGroup: (key: string) => void;
  onCollapseGroup: (key: string) => void;
  tagNames: (ids: number[]) => string;
}

type EvolutionFlowNode = Node<WorkNodeData>;

function WorkNode({ data }: NodeProps<EvolutionFlowNode>) {
  const { tree, item, onOpen, onToggle } = data;
  if (!item || tree.entityId === undefined) return null;
  const year = yearLabel(item.date);
  const edge = tree.edge;
  const explanationText = edge
    ? `Inferred from tag similarity ${edge.score.toFixed(2)}, ${edge.shared} shared tags` +
      (edge.topTags.length ? `; strongest: ${data.tagNames(edge.topTags)}` : "")
    : "Root of an inferred branch";
  return (
    <div className="evo-node" title={explanationText}>
      <Handle type="target" position={Position.Left} className="hidden-handle" isConnectable={false} />
      <Handle type="source" position={Position.Right} className="hidden-handle" isConnectable={false} />
      <button
        type="button"
        className="evo-open"
        onClick={() => onOpen(item.id)}
        aria-label={`Open details for ${item.label}${year ? `, ${year}` : ""}`}
      >
        <span className="evo-kind">
          <SvgIcon name={kindIconName(item.kind)} title="" size={14} />
        </span>
        <span className="evo-label">{item.label}</span>
        <span className="evo-year">{year || "—"}</span>
      </button>
      {tree.childCount > 0 ? (
        <button
          type="button"
          className="evo-toggle"
          onClick={(event) => {
            event.stopPropagation();
            onToggle(item.id);
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
      title={`${placeholder.childIds.length} hidden related works of the same kind and similar tag profile`}
    >
      <Handle type="target" position={Position.Left} className="hidden-handle" isConnectable={false} />
      +{placeholder.childIds.length}
    </button>
  );
}

const nodeTypes = { work: WorkNode, placeholder: PlaceholderNode };

function EvolutionCanvas({
  data,
  tagIndex,
  settings,
  forest,
  onOpen,
}: {
  data: AppData;
  tagIndex: TagIndex;
  settings: Settings;
  forest: EvolutionForest;
  onOpen: OpenHandler;
}) {
  const evolutionSettings: EvolutionSettings = settings.evolution;
  const [state, setState] = useState(() => loadStoredState(evolutionSettings.maxInitialRoots));
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const { fitView, setCenter, setViewport } = useReactFlow();
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
    const visibleForest = buildVisibleForest(
      forest,
      data.catalogById,
      tagIndex,
      evolutionSettings,
      viewState,
    );
    return layoutForest(visibleForest);
  }, [forest, data.catalogById, tagIndex, evolutionSettings, viewState]);

  const tagNames = useCallback(
    (ids: number[]) => ids.map((id) => data.tagById.get(id)?.name || `#${id}`).join(", "),
    [data.tagById],
  );

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
          item: placed.node.entityId !== undefined ? data.catalogById.get(placed.node.entityId) : undefined,
          onOpen,
          onToggle,
          onExpandGroup,
          onCollapseGroup,
          tagNames,
        },
      })),
    [layout, data.catalogById, onOpen, onToggle, onExpandGroup, onCollapseGroup, tagNames],
  );

  const edges: Edge[] = useMemo(
    () =>
      layout.edges.map((edge) => ({
        id: edge.key,
        source: edge.sourceKey,
        target: edge.targetKey,
        type: "smoothstep",
        focusable: false,
      })),
    [layout],
  );

  // Focus a node after a search reveal once the new layout is in place.
  useEffect(() => {
    if (focusTarget.current === null) return;
    const key = workKey(focusTarget.current);
    const placed = layout.nodes.find((candidate) => candidate.node.key === key);
    if (placed) {
      setCenter(placed.x + 110, placed.y + 20, { zoom: 1, duration: 300 });
      focusTarget.current = null;
    }
  }, [layout, setCenter]);

  const searchMatches = useMemo(() => {
    const query = debouncedSearch.trim().toLowerCase();
    if (query.length < 2) return [];
    const matches: CatalogItem[] = [];
    for (const item of data.catalog) {
      if (item.label.toLowerCase().includes(query)) {
        matches.push(item);
        if (matches.length >= 8) break;
      }
    }
    return matches;
  }, [debouncedSearch, data.catalog]);

  function focusWork(id: number) {
    const reveal = revealWork(id, forest, data.catalogById, tagIndex, evolutionSettings);
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
    <div className="graph-view" data-testid="evolution-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.05}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        proOptions={{ hideAttribution: false }}
      >
        <Background />
        <Controls showInteractive={false} />
        <Panel position="top-left" className="graph-panel">
          <p className="graph-disclaimer">
            Branches are inferred from date and tag similarity. They do not prove direct influence.
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
                  {searchMatches.map((item) => (
                    <li key={item.id}>
                      <button type="button" onClick={() => focusWork(item.id)}>
                        {item.label} {yearLabel(item.date) ? `(${yearLabel(item.date)})` : ""}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <button type="button" onClick={() => fitView({ duration: 300 })}>
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
                    visibleRootCount: Math.min(totalRoots, current.visibleRootCount + evolutionSettings.maxInitialRoots),
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
  tagIndex,
  settings,
  onOpen,
}: {
  data: AppData;
  tagIndex: TagIndex;
  settings: Settings;
  onOpen: OpenHandler;
}) {
  const forest = useMemo(() => (data.evolution ? buildForest(data.evolution) : null), [data.evolution]);

  if (!data.evolution || !forest) {
    return (
      <section className="empty">
        Evolution data is not available. Regenerate the static exports with the Python export command.
      </section>
    );
  }

  return (
    <ReactFlowProvider>
      <EvolutionCanvas data={data} tagIndex={tagIndex} settings={settings} forest={forest} onOpen={onOpen} />
    </ReactFlowProvider>
  );
}

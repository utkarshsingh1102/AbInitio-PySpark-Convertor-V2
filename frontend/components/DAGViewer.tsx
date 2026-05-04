"use client";
import { useMemo } from "react";
import dagre from "@dagrejs/dagre";
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  Position,
  Node,
  Edge,
} from "reactflow";
import "reactflow/dist/style.css";
import type { DAG } from "@/lib/api";

// ── component palette (light-mode) ────────────────────────────────────────
// [accent, fill] — accent paints the type label and the left bar; fill
// is the soft tint behind the body.
const TYPE_COLORS: Record<string, [string, string]> = {
  InputFile:         ["#16A34A", "#F0FDF4"],
  OutputFile:        ["#DC2626", "#FEF2F2"],
  LookupFile:        ["#059669", "#ECFDF5"],
  IntermediateFile:  ["#65A30D", "#F7FEE7"],
  Reformat:          ["#2563EB", "#EFF6FF"],
  Filter:            ["#9333EA", "#FAF5FF"],
  Sort:              ["#0284C7", "#F0F9FF"],
  SortWithinGroups:  ["#0284C7", "#F0F9FF"],
  DedupSorted:       ["#7C3AED", "#F5F3FF"],
  Rollup:            ["#0891B2", "#ECFEFF"],
  Aggregate:         ["#0891B2", "#ECFEFF"],
  Scan:              ["#0891B2", "#ECFEFF"],
  Normalize:         ["#EA580C", "#FFF7ED"],
  DenormalizeSorted: ["#EA580C", "#FFF7ED"],
  Join:              ["#D97706", "#FFFBEB"],
  Lookup:            ["#CA8A04", "#FEFCE8"],
  MatchSorted:       ["#D97706", "#FFFBEB"],
  Replicate:         ["#64748B", "#F8FAFC"],
  Gather:            ["#475569", "#F8FAFC"],
  Concatenate:       ["#475569", "#F8FAFC"],
  RunProgram:        ["#B91C1C", "#FEF2F2"],
  Trash:             ["#334155", "#F1F5F9"],
};

const FALLBACK: [string, string] = ["#6F6D65", "#FBFAF6"];
const LEFT_PORT_COLOR  = "#0891B2";   // cyan-600  — Join in_left
const RIGHT_PORT_COLOR = "#DA7756";   // coral-500 — Join in_right
const DEFAULT_EDGE_COLOR = "#A6A39A";

// ── node geometry ─────────────────────────────────────────────────────────
const NODE_WIDTH  = 200;
const NODE_HEIGHT = 76;
const RANK_SEP    = 110;   // horizontal gap between layers
const NODE_SEP    = 28;    // vertical gap between siblings on the same layer
const EDGE_SEP    = 24;    // routing buffer between edges

export function DAGViewer({ dag }: { dag: DAG }) {
  const { nodes, edges } = useMemo(() => layout(dag), [dag]);
  return (
    <div className="w-full h-[500px] rounded-xl bg-white border border-cream-400 shadow-card overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
        maxZoom={2}
      >
        <Background color="#E6E4D9" gap={22} size={1.2} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

// ── dagre-based hierarchical layout ──────────────────────────────────────
function layout(dag: DAG): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: "LR",
    ranksep: RANK_SEP,
    nodesep: NODE_SEP,
    edgesep: EDGE_SEP,
    align: "UL",
    marginx: 20,
    marginy: 20,
  });
  g.setDefaultEdgeLabel(() => ({}));

  // Pin every source (no incoming edges) to the leftmost rank, and every
  // sink (no outgoing edges) to the rightmost rank — so all reads sit on
  // one column and all writes sit on the same column.
  const incoming: Record<string, number> = {};
  const outgoing: Record<string, number> = {};
  for (const n of dag.nodes) {
    incoming[n.id] = 0;
    outgoing[n.id] = 0;
  }
  for (const e of dag.edges) {
    incoming[e.to] = (incoming[e.to] ?? 0) + 1;
    outgoing[e.from] = (outgoing[e.from] ?? 0) + 1;
  }

  for (const n of dag.nodes) {
    const opts: Record<string, unknown> = { width: NODE_WIDTH, height: NODE_HEIGHT };
    if (incoming[n.id] === 0 && outgoing[n.id] > 0)      opts.rank = "min";
    else if (outgoing[n.id] === 0 && incoming[n.id] > 0) opts.rank = "max";
    g.setNode(n.id, opts);
  }
  for (const e of dag.edges) {
    g.setEdge(e.from, e.to);
  }

  dagre.layout(g);

  // Snap every source to the leftmost x and every sink to the rightmost x.
  // dagre's `rank: min/max` constraint isn't strict — it doesn't pull a
  // node further than its natural depth allows. Doing it post-layout
  // guarantees alignment regardless of branch lengths.
  let maxSinkX = -Infinity;
  let minSourceX = Infinity;
  for (const n of dag.nodes) {
    const dn = g.node(n.id);
    if (!dn) continue;
    if (incoming[n.id] === 0 && outgoing[n.id] > 0) {
      minSourceX = Math.min(minSourceX, dn.x);
    } else if (outgoing[n.id] === 0 && incoming[n.id] > 0) {
      maxSinkX = Math.max(maxSinkX, dn.x);
    }
  }

  const nodes: Node[] = dag.nodes.map((n) => {
    const dn = g.node(n.id);
    const [accent, fill] = TYPE_COLORS[n.type] ?? FALLBACK;
    let x = dn.x;
    if (incoming[n.id] === 0 && outgoing[n.id] > 0 && Number.isFinite(minSourceX)) {
      x = minSourceX;
    } else if (outgoing[n.id] === 0 && incoming[n.id] > 0 && Number.isFinite(maxSinkX)) {
      x = maxSinkX;
    }
    return {
      id: n.id,
      data: { label: <NodeLabel name={n.name} type={n.type} accent={accent} /> },
      position: { x: x - NODE_WIDTH / 2, y: dn.y - NODE_HEIGHT / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        background: fill,
        border: `1px solid ${accent}33`,
        borderLeft: `3px solid ${accent}`,
        color: "#1F1E1B",
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        borderRadius: 10,
        padding: "10px 12px",
        boxShadow: "0 1px 3px rgba(31, 30, 27, 0.06)",
        fontFamily: "Inter, system-ui, sans-serif",
      },
    };
  });

  const edges: Edge[] = dag.edges.map((e, i) => {
    const stroke =
      e.to_port === "in_left"  ? LEFT_PORT_COLOR :
      e.to_port === "in_right" ? RIGHT_PORT_COLOR :
      DEFAULT_EDGE_COLOR;
    return {
      id: `e${i}`,
      source: e.from,
      target: e.to,
      type: "smoothstep",
      animated: true,
      pathOptions: { borderRadius: 12 } as any,
      label: e.to_port && e.to_port !== "in" ? e.to_port : undefined,
      labelStyle: {
        fill: stroke,
        fontSize: 10,
        fontFamily: "JetBrains Mono, monospace",
      },
      labelBgStyle: { fill: "#FFFFFF" },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 4,
      markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 16, height: 16 },
      style: { stroke, strokeWidth: 1.5 },
    };
  });

  return { nodes, edges };
}

function NodeLabel({ name, type, accent }: { name: string; type: string; accent: string }) {
  return (
    <div className="text-left">
      <div
        className="text-[10px] uppercase tracking-[0.08em] font-medium"
        style={{ color: accent }}
      >
        {type}
      </div>
      <div className="font-semibold text-sm text-ink-700 mt-0.5 truncate">{name}</div>
    </div>
  );
}

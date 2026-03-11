"""
Graph viewer – generates a self-contained HTML file with React Flow
(loaded from CDN) and opens it in the default browser.

Replicates the Dylogy design-system graph theme:
  causation-colored badges, card-style nodes, dagre TB layout,
  dot background, minimap, controls, and a legend.
"""

import json
import os
import tempfile
import webbrowser
from typing import Any


# Tailwind hex equivalents for each causation type
CAUSE_COLORS = {
    "PrimaryCause":        {"text": "#22c55e", "bg": "#f0fdf4", "ring": "#4ade80"},
    "SecondaryCause":      {"text": "#06b6d4", "bg": "#ecfeff", "ring": "#22d3ee"},
    "TriggerEvent":        {"text": "#10b981", "bg": "#ecfdf5", "ring": "#34d399"},
    "DirectConsequence":   {"text": "#3b82f6", "bg": "#eff6ff", "ring": "#60a5fa"},
    "IndirectConsequence": {"text": "#f59e0b", "bg": "#fffbeb", "ring": "#fbbf24"},
    "MitigationAction":    {"text": "#ec4899", "bg": "#fdf2f8", "ring": "#f472b6"},
    "ResolutionProposed":  {"text": "#d946ef", "bg": "#fdf4ff", "ring": "#e879f9"},
    "ResolutionCompleted": {"text": "#84cc16", "bg": "#f7fee7", "ring": "#a3e635"},
    "default":             {"text": "#6b7280", "bg": "#f9fafb", "ring": "#9ca3af"},
}


def _extract_value(prop: Any) -> Any:
    """Extract the raw value from a graph property dict."""
    if prop is None:
        return None
    if isinstance(prop, dict):
        return prop.get("value")
    return prop


def _transform_graph_data(graph_data: dict, document_name: str) -> dict:
    """Convert the API graph response into a viewer-friendly dict."""
    gd = graph_data.get("graphData", {})
    nodes_raw = gd.get("nodes", [])
    edges_raw = gd.get("edges", [])
    properties = gd.get("properties", {})

    viewer: dict[str, Any] = {
        "documentName": document_name,
        "properties": {},
        "nodes": [],
        "edges": [],
        "causeColors": CAUSE_COLORS,
    }

    for k, v in properties.items():
        viewer["properties"][k] = _extract_value(v)

    for node in nodes_raw:
        nid = str(node.get("nodeId", node.get("id", "")))
        props = node.get("properties", {})
        viewer["nodes"].append({
            "id": nid,
            "label": _extract_value(props.get("label")) or "Untitled",
            "eventDescription": _extract_value(props.get("eventDescription")) or "",
            "eventCategory": _extract_value(props.get("eventCategory")) or "",
            "dateTime": _extract_value(props.get("dateTime")) or "",
            "causation": _extract_value(props.get("causation")) or "default",
        })

    for i, edge in enumerate(edges_raw):
        delay = _extract_value(edge.get("properties", {}).get("delay"))
        relation = edge.get("relation")
        # API uses nodeOriginId / nodeDestinationId
        source = edge.get("nodeOriginId") or edge.get("sourceNodeId")
        target = edge.get("nodeDestinationId") or edge.get("targetNodeId")
        label_parts = []
        if relation:
            label_parts.append(relation.replace("_", " ").title())
        if delay is not None:
            label_parts.append(f"{delay} days")
        viewer["edges"].append({
            "id": f"e{i}",
            "source": str(source) if source is not None else "",
            "target": str(target) if target is not None else "",
            "label": " · ".join(label_parts) if label_parts else None,
        })

    return viewer


def open_graph_viewer(graph_data: dict, document_name: str) -> str:
    """Build the HTML, write it to a temp file, and open the browser.
    Returns the path to the generated file."""
    viewer_data = _transform_graph_data(graph_data, document_name)
    html = _build_html(viewer_data)

    fd, path = tempfile.mkstemp(suffix=".html", prefix="dylogy-graph-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)

    webbrowser.open(f"file://{path}")
    return path


def _build_html(viewer_data: dict) -> str:
    data_json = json.dumps(viewer_data, ensure_ascii=False)
    title = viewer_data["documentName"]
    return (
        HTML_TEMPLATE
        .replace("__GRAPH_DATA__", data_json)
        .replace("__TITLE__", title)
    )


# ---------------------------------------------------------------------------
# Self-contained HTML template
# ---------------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ – Dylogy Graph</title>

<!-- React Flow stylesheet -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@xyflow/react@12/dist/style.css">

<style>
/* ── Reset & base ──────────────────────────────────────────────────────── */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #root { width: 100%; height: 100vh; overflow: hidden; }
body {
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #fafafa;
  color: #0f172a;
}

/* ── Header bar ────────────────────────────────────────────────────────── */
.header-bar {
  position: fixed; top: 0; left: 0; right: 0;
  height: 52px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  display: flex; align-items: center;
  padding: 0 1.25rem;
  z-index: 100;
  gap: 1.5rem;
}
.header-bar h1 { font-size: 0.875rem; font-weight: 600; white-space: nowrap; }
.header-props { display: flex; gap: 1.25rem; font-size: 0.75rem; color: #64748b; flex-wrap: wrap; }
.header-props .pv { font-weight: 600; color: #0f172a; }

/* ── Flow container ────────────────────────────────────────────────────── */
.flow-container { width: 100%; height: calc(100vh - 52px); margin-top: 52px; }

/* ── Graph node ────────────────────────────────────────────────────────── */
.graph-node {
  min-width: 280px;
  max-width: 28rem;
  border-radius: 0.75rem;
  border: 1px solid #e2e8f0;
  background: #fff;
  padding: 1rem;
  box-shadow: 0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -2px rgba(0,0,0,.1);
  transition: box-shadow .2s, border-color .2s;
}
.graph-node.selected { border-color: transparent; }

.cause-badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.675rem;
  font-weight: 600;
  letter-spacing: 0.025em;
}

.node-title {
  margin: 0.75rem 0 0.25rem;
  font-weight: 500;
  font-size: 0.875rem;
  line-height: 1.25rem;
}

.node-desc {
  font-size: 0.75rem;
  line-height: 1.125rem;
  color: #64748b;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.node-footer {
  margin-top: 0.75rem;
  display: flex; gap: 1rem;
  border-top: 1px solid #e2e8f0;
  padding-top: 0.75rem;
  font-size: 0.75rem;
  color: #64748b;
}
.node-meta { display: flex; align-items: center; gap: 0.3rem; }
.node-meta svg { width: 0.75rem; height: 0.75rem; flex-shrink: 0; }
.node-meta-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px; }

/* ── Edge overrides ────────────────────────────────────────────────────── */
.react-flow__edge-path { stroke: #cbd5e1; stroke-width: 2; }
.react-flow__edge.selected .react-flow__edge-path,
.react-flow__edge:hover .react-flow__edge-path { stroke: #0f172a; }
.react-flow__edge-text { font-size: 11px; fill: #64748b; }
.react-flow__edge-textbg { fill: #fff; stroke: #e2e8f0; stroke-width: 1; }

/* ── Legend ─────────────────────────────────────────────────────────────── */
.legend {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.75rem 0.875rem;
  font-size: 0.7rem;
  display: flex; flex-direction: column; gap: 0.4rem;
  color: #334155;
}
.legend-title { font-weight: 600; margin-bottom: 0.15rem; font-size: 0.725rem; }
.legend-item { display: flex; align-items: center; gap: 0.5rem; }
.legend-dot { width: 8px; height: 8px; border-radius: 9999px; flex-shrink: 0; }

/* ── Empty state ───────────────────────────────────────────────────────── */
.empty-state {
  display: flex; align-items: center; justify-content: center;
  height: 100vh; color: #64748b; font-size: 1rem;
}
</style>
</head>
<body>
<div id="root"></div>

<script type="module">
// ── Imports ───────────────────────────────────────────────────────────────
import React, { useMemo } from 'https://esm.sh/react@18.3.1'
import { createRoot }     from 'https://esm.sh/react-dom@18.3.1/client'
import {
  ReactFlow, ReactFlowProvider,
  Background, Controls, MiniMap, Panel,
  Handle, Position, MarkerType,
} from 'https://esm.sh/@xyflow/react@12?deps=react@18.3.1,react-dom@18.3.1'
import dagre from 'https://esm.sh/@dagrejs/dagre@1.1.4'
import htm   from 'https://esm.sh/htm@3.1.1'

const html = htm.bind(React.createElement)

// ── Data injected by Python ──────────────────────────────────────────────
const DATA = __GRAPH_DATA__
const CAUSE_COLORS = DATA.causeColors

// ── Helpers ──────────────────────────────────────────────────────────────
const HANDLE_STYLE = {
  background: 'none', border: 'none',
  width: 1, height: 1, minWidth: 1, minHeight: 1,
}

function fmtDate(dt) {
  if (!dt) return 'N/A'
  try {
    return new Date(dt).toLocaleDateString('en-GB', {
      year: 'numeric', month: 'short', day: 'numeric',
    })
  } catch (_) { return dt }
}

// ── Inline SVG icons (Lucide: CalendarDays & Info) ───────────────────────
function CalendarIcon() {
  return html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round">
    <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/>
    <line x1="16" x2="16" y1="2" y2="6"/>
    <line x1="8" x2="8" y1="2" y2="6"/>
    <line x1="3" x2="21" y1="10" y2="10"/>
  </svg>`
}
function InfoIcon() {
  return html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <path d="M12 16v-4"/>
    <path d="M12 8h.01"/>
  </svg>`
}

// ── Custom Node ──────────────────────────────────────────────────────────
function CustomNode({ data, selected }) {
  const c = CAUSE_COLORS[data.causation] || CAUSE_COLORS.default
  const ring = selected
    ? { boxShadow: '0 0 0 2px #fff, 0 0 0 4px ' + c.ring }
    : {}

  return html`
    <div className=${'graph-node' + (selected ? ' selected' : '')} style=${ring}>
      <${Handle} type="target" position=${Position.Top} style=${HANDLE_STYLE} />

      <span className="cause-badge" style=${{ background: c.bg, color: c.text }}>
        ${data.causation}
      </span>

      <h3 className="node-title">${data.label}</h3>

      <p className="node-desc">${data.eventDescription}</p>

      <div className="node-footer">
        <span className="node-meta">
          <${CalendarIcon}/>
          <span className="node-meta-text">${fmtDate(data.dateTime)}</span>
        </span>
        <span className="node-meta" style=${{ flex: 1, overflow: 'hidden' }}>
          <${InfoIcon}/>
          <span className="node-meta-text">${data.eventCategory}</span>
        </span>
      </div>

      <${Handle} type="source" position=${Position.Bottom} style=${HANDLE_STYLE} />
    </div>
  `
}

// Must be defined outside the component to avoid re-creation
const nodeTypes = { custom: CustomNode }

// ── Dagre layout ─────────────────────────────────────────────────────────
function applyLayout(nodes, edges) {
  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 120 })

  const W = 350, H = 180
  const nodeIds = new Set(nodes.map(n => n.id))
  nodes.forEach(n => g.setNode(n.id, { width: W, height: H }))
  edges.forEach(e => {
    if (e.source && e.target && nodeIds.has(e.source) && nodeIds.has(e.target))
      g.setEdge(e.source, e.target)
  })
  dagre.layout(g)

  return nodes.map(n => {
    const { x, y } = g.node(n.id)
    return { ...n, position: { x: x - W / 2, y: y - H / 2 } }
  })
}

// ── Build React Flow data from injected DATA ─────────────────────────────
function buildFlow() {
  const nodes = DATA.nodes.map(n => ({
    id: n.id,
    type: 'custom',
    position: { x: 0, y: 0 },
    data: n,
  }))

  const edges = DATA.edges.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#cbd5e1' },
    style: { stroke: '#cbd5e1', strokeWidth: 2 },
  }))

  return { nodes: applyLayout(nodes, edges), edges }
}

// ── App ──────────────────────────────────────────────────────────────────
function App() {
  const { nodes, edges } = useMemo(buildFlow, [])
  const props = DATA.properties

  if (!nodes.length) {
    return html`<div className="empty-state">
      This document produced an empty graph.
    </div>`
  }

  const causations = [...new Set(DATA.nodes.map(n => n.causation))]

  return html`
    <div style=${{ width: '100%', height: '100%' }}>
      <!-- header -->
      <div className="header-bar">
        <h1>${DATA.documentName}</h1>
        <div className="header-props">
          ${Object.entries(props).map(([k, v]) =>
            v != null && html`
              <span key=${k}>${k}: <span className="pv">${
                typeof v === 'number' ? v.toLocaleString() : v
              }</span></span>
            `
          )}
          <span>Nodes: <span className="pv">${nodes.length}</span></span>
          <span>Edges: <span className="pv">${edges.length}</span></span>
        </div>
      </div>

      <!-- graph -->
      <div className="flow-container">
        <${ReactFlowProvider}>
          <${ReactFlow}
            nodes=${nodes}
            edges=${edges}
            nodeTypes=${nodeTypes}
            fitView
            minZoom=${0.1}
            maxZoom=${2}
            nodesDraggable=${true}
            nodesConnectable=${false}
            elementsSelectable=${true}
            edgesReconnectable=${false}
            defaultEdgeOptions=${{ selectable: true, deletable: false, focusable: true }}
          >
            <${Background} variant="dots" />
            <${Controls} />
            <${MiniMap} />

            <${Panel} position="bottom-left">
              <div className="legend">
                <div className="legend-title">Causation</div>
                ${causations.map(cause => {
                  const col = CAUSE_COLORS[cause] || CAUSE_COLORS.default
                  return html`
                    <div className="legend-item" key=${cause}>
                      <div className="legend-dot" style=${{ background: col.text }} />
                      <span>${cause}</span>
                    </div>
                  `
                })}
              </div>
            <//>
          <//>
        <//>
      </div>
    </div>
  `
}

// ── Mount ────────────────────────────────────────────────────────────────
createRoot(document.getElementById('root')).render(html`<${App} />`)
</script>
</body>
</html>"""

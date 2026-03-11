"""
Custom MCP tools for Dylogy: graph_to_mermaid, graph_stats,
compare_document_graphs, export_environment_report.
"""

import base64
import json
import webbrowser
import zlib
from typing import Any

from graph_viewer import _extract_value


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_node_label(node: dict) -> str:
    props = node.get("properties", {})
    return _extract_value(props.get("label")) or f"Node {node.get('nodeId', '?')}"


def _get_node_prop(node: dict, key: str) -> Any:
    return _extract_value(node.get("properties", {}).get(key))


def _parse_graph(data: dict) -> tuple[list[dict], list[dict], dict]:
    """Extract nodes, edges, properties from a graph API response."""
    gd = data.get("graphData", {})
    return gd.get("nodes", []), gd.get("edges", []), gd.get("properties", {})


# ── graph_to_mermaid ─────────────────────────────────────────────────────────

def graph_to_mermaid(graph_data: dict, document_name: str = "Document") -> str:
    """Convert a document graph to a Mermaid flowchart string."""
    nodes, edges, properties = _parse_graph(graph_data)

    if not nodes:
        return "graph TD\n  empty[No nodes in graph]"

    lines = ["graph TD"]

    # Style classes for causation types
    causation_styles = {
        "PrimaryCause":        "fill:#f0fdf4,stroke:#22c55e,color:#15803d",
        "SecondaryCause":      "fill:#ecfeff,stroke:#06b6d4,color:#0e7490",
        "TriggerEvent":        "fill:#ecfdf5,stroke:#10b981,color:#047857",
        "DirectConsequence":   "fill:#eff6ff,stroke:#3b82f6,color:#1d4ed8",
        "IndirectConsequence": "fill:#fffbeb,stroke:#f59e0b,color:#b45309",
        "MitigationAction":    "fill:#fdf2f8,stroke:#ec4899,color:#be185d",
        "ResolutionProposed":  "fill:#fdf4ff,stroke:#d946ef,color:#a21caf",
        "ResolutionCompleted": "fill:#f7fee7,stroke:#84cc16,color:#4d7c0f",
    }

    # Add nodes
    for node in sorted(nodes, key=lambda n: n.get("nodeId", 0)):
        nid = node.get("nodeId", "?")
        label = _get_node_label(node).replace('"', "'")
        causation = _get_node_prop(node, "causation") or "default"
        lines.append(f'  n{nid}["{label}"]')

    lines.append("")

    # Add edges
    for edge in edges:
        src = edge.get("nodeOriginId")
        dst = edge.get("nodeDestinationId")
        rel = edge.get("relation", "")
        rel_label = rel.replace("_", " ").title()
        lines.append(f'  n{src} -->|"{rel_label}"| n{dst}')

    lines.append("")

    # Add style classes
    for node in nodes:
        nid = node.get("nodeId", "?")
        causation = _get_node_prop(node, "causation") or "default"
        style = causation_styles.get(causation)
        if style:
            lines.append(f"  style n{nid} {style}")

    return "\n".join(lines)


def mermaid_live_url(mermaid_code: str) -> str:
    """Encode a Mermaid diagram into a mermaid.live playground URL.

    Uses pako (zlib) compression + URL-safe base64, matching the format
    used by https://mermaid.live and https://mermaid.ai/play.
    """
    state = json.dumps({
        "code": mermaid_code,
        "mermaid": {"theme": "default"},
        "autoSync": True,
        "updateDiagram": True,
    })
    compressed = zlib.compress(state.encode("utf-8"), 9)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return f"https://mermaid.live/edit#pako:{encoded}"


def open_mermaid_viewer(mermaid_code: str) -> str:
    """Build the mermaid.live URL and open it in the default browser.

    Returns the URL.
    """
    url = mermaid_live_url(mermaid_code)
    webbrowser.open(url)
    return url


# ── graph_stats ──────────────────────────────────────────────────────────────

def graph_stats(graph_data: dict) -> str:
    """Compute analytics on a document graph."""
    nodes, edges, properties = _parse_graph(graph_data)

    if not nodes:
        return "Empty graph – no statistics to compute."

    node_count = len(nodes)
    edge_count = len(edges)

    # Build adjacency for analysis
    adj: dict[int, list[int]] = {}
    in_degree: dict[int, int] = {}
    out_degree: dict[int, int] = {}

    for node in nodes:
        nid = node.get("nodeId")
        adj[nid] = []
        in_degree[nid] = 0
        out_degree[nid] = 0

    for edge in edges:
        src = edge.get("nodeOriginId")
        dst = edge.get("nodeDestinationId")
        if src in adj:
            adj[src].append(dst)
            out_degree[src] = out_degree.get(src, 0) + 1
        if dst in in_degree:
            in_degree[dst] = in_degree.get(dst, 0) + 1

    # Root nodes (no incoming edges)
    roots = [nid for nid, deg in in_degree.items() if deg == 0]

    # Leaf nodes (no outgoing edges)
    leaves = [nid for nid, deg in out_degree.items() if deg == 0]

    # Hub nodes (highest total degree)
    total_degree = {nid: in_degree.get(nid, 0) + out_degree.get(nid, 0) for nid in adj}
    hub_id = max(total_degree, key=total_degree.get)

    # Longest path (DFS)
    memo: dict[int, list[int]] = {}

    def longest_path(nid: int, visited: set) -> list[int]:
        if nid in memo:
            return memo[nid]
        visited.add(nid)
        best = [nid]
        for neighbor in adj.get(nid, []):
            if neighbor not in visited:
                candidate = [nid] + longest_path(neighbor, visited)
                if len(candidate) > len(best):
                    best = candidate
        visited.discard(nid)
        memo[nid] = best
        return best

    longest = []
    for root in (roots or list(adj.keys())):
        path = longest_path(root, set())
        if len(path) > len(longest):
            longest = path

    # Causation distribution
    causation_counts: dict[str, int] = {}
    for node in nodes:
        c = _get_node_prop(node, "causation") or "Unknown"
        causation_counts[c] = causation_counts.get(c, 0) + 1

    # Category distribution
    category_counts: dict[str, int] = {}
    for node in nodes:
        cat = _get_node_prop(node, "eventCategory") or "Unknown"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Relation type distribution
    relation_counts: dict[str, int] = {}
    for edge in edges:
        rel = edge.get("relation", "Unknown")
        relation_counts[rel] = relation_counts.get(rel, 0) + 1

    # Global properties
    global_props = {}
    for k, v in properties.items():
        global_props[k] = _extract_value(v)

    # Build node lookup
    node_map = {n.get("nodeId"): _get_node_label(n) for n in nodes}

    # Format output
    lines = [
        "## Graph Statistics",
        "",
        f"- **Nodes:** {node_count}",
        f"- **Edges:** {edge_count}",
        f"- **Density:** {edge_count / (node_count * (node_count - 1)) * 100:.1f}%" if node_count > 1 else f"- **Density:** N/A",
        f"- **Sub-graphs merged:** {graph_data.get('numGraphs', 'N/A')}",
        f"- **Merge method:** {graph_data.get('mergeMethod', 'N/A')}",
    ]

    if global_props:
        lines += ["", "### Global Properties"]
        for k, v in global_props.items():
            if v is not None:
                lines.append(f"- **{k}:** {v}")

    lines += [
        "",
        "### Topology",
        f"- **Root nodes** (no incoming): {', '.join(node_map.get(r, str(r)) for r in roots) or 'None (cyclic)'}",
        f"- **Leaf nodes** (no outgoing): {', '.join(node_map.get(l, str(l)) for l in leaves) or 'None'}",
        f"- **Hub node** (most connections): {node_map.get(hub_id, str(hub_id))} ({total_degree[hub_id]} connections)",
        f"- **Longest causal chain:** {len(longest)} nodes",
    ]

    if longest:
        chain_labels = [f"  {i+1}. {node_map.get(nid, str(nid))}" for i, nid in enumerate(longest)]
        lines += ["", "### Longest Chain"] + chain_labels

    lines += ["", "### Causation Distribution"]
    for cause, count in sorted(causation_counts.items(), key=lambda x: -x[1]):
        bar = "█" * count
        lines.append(f"  {cause}: {count} {bar}")

    lines += ["", "### Event Category Distribution"]
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {cat}: {count}")

    lines += ["", "### Edge Relation Types"]
    for rel, count in sorted(relation_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {rel}: {count}")

    return "\n".join(lines)


# ── compare_document_graphs ──────────────────────────────────────────────────

def compare_document_graphs(
    graph_a: dict, name_a: str,
    graph_b: dict, name_b: str,
) -> str:
    """Compare two document graphs and produce a structured diff."""
    nodes_a, edges_a, props_a = _parse_graph(graph_a)
    nodes_b, edges_b, props_b = _parse_graph(graph_b)

    lines = [
        "## Graph Comparison",
        "",
        f"| Metric | {name_a} | {name_b} |",
        "|--------|" + "-" * (len(name_a) + 2) + "|" + "-" * (len(name_b) + 2) + "|",
        f"| Nodes | {len(nodes_a)} | {len(nodes_b)} |",
        f"| Edges | {len(edges_a)} | {len(edges_b)} |",
        f"| Sub-graphs | {graph_a.get('numGraphs', 'N/A')} | {graph_b.get('numGraphs', 'N/A')} |",
    ]

    # Global property comparison
    all_prop_keys = set()
    for k, v in props_a.items():
        if _extract_value(v) is not None:
            all_prop_keys.add(k)
    for k, v in props_b.items():
        if _extract_value(v) is not None:
            all_prop_keys.add(k)

    if all_prop_keys:
        for k in sorted(all_prop_keys):
            va = _extract_value(props_a.get(k)) or "–"
            vb = _extract_value(props_b.get(k)) or "–"
            lines.append(f"| {k} | {va} | {vb} |")

    # Causation comparison
    def causation_dist(nodes):
        d = {}
        for n in nodes:
            c = _get_node_prop(n, "causation") or "Unknown"
            d[c] = d.get(c, 0) + 1
        return d

    ca = causation_dist(nodes_a)
    cb = causation_dist(nodes_b)
    all_causes = sorted(set(list(ca.keys()) + list(cb.keys())))

    lines += [
        "",
        "### Causation Distribution",
        "",
        f"| Causation | {name_a} | {name_b} |",
        "|-----------|" + "-" * (len(name_a) + 2) + "|" + "-" * (len(name_b) + 2) + "|",
    ]
    for cause in all_causes:
        lines.append(f"| {cause} | {ca.get(cause, 0)} | {cb.get(cause, 0)} |")

    # Category comparison
    def category_dist(nodes):
        d = {}
        for n in nodes:
            c = _get_node_prop(n, "eventCategory") or "Unknown"
            d[c] = d.get(c, 0) + 1
        return d

    cat_a = category_dist(nodes_a)
    cat_b = category_dist(nodes_b)
    all_cats = sorted(set(list(cat_a.keys()) + list(cat_b.keys())))

    lines += [
        "",
        "### Event Category Distribution",
        "",
        f"| Category | {name_a} | {name_b} |",
        "|----------|" + "-" * (len(name_a) + 2) + "|" + "-" * (len(name_b) + 2) + "|",
    ]
    for cat in all_cats:
        lines.append(f"| {cat} | {cat_a.get(cat, 0)} | {cat_b.get(cat, 0)} |")

    # Relation comparison
    def relation_dist(edges):
        d = {}
        for e in edges:
            r = e.get("relation", "Unknown")
            d[r] = d.get(r, 0) + 1
        return d

    rel_a = relation_dist(edges_a)
    rel_b = relation_dist(edges_b)
    all_rels = sorted(set(list(rel_a.keys()) + list(rel_b.keys())))

    lines += [
        "",
        "### Edge Relations",
        "",
        f"| Relation | {name_a} | {name_b} |",
        "|----------|" + "-" * (len(name_a) + 2) + "|" + "-" * (len(name_b) + 2) + "|",
    ]
    for rel in all_rels:
        lines.append(f"| {rel} | {rel_a.get(rel, 0)} | {rel_b.get(rel, 0)} |")

    # Shared event categories
    shared_cats = set(cat_a.keys()) & set(cat_b.keys())
    only_a_cats = set(cat_a.keys()) - set(cat_b.keys())
    only_b_cats = set(cat_b.keys()) - set(cat_a.keys())

    lines += [
        "",
        "### Category Overlap",
        f"- **Shared categories ({len(shared_cats)}):** {', '.join(sorted(shared_cats)) or 'None'}",
        f"- **Only in {name_a} ({len(only_a_cats)}):** {', '.join(sorted(only_a_cats)) or 'None'}",
        f"- **Only in {name_b} ({len(only_b_cats)}):** {', '.join(sorted(only_b_cats)) or 'None'}",
    ]

    # Structural similarity (Jaccard on causation patterns)
    set_a = set(ca.keys())
    set_b = set(cb.keys())
    if set_a or set_b:
        jaccard = len(set_a & set_b) / len(set_a | set_b) * 100
        lines += [
            "",
            "### Structural Similarity",
            f"- **Causation pattern similarity (Jaccard):** {jaccard:.0f}%",
        ]

    return "\n".join(lines)


# ── export_environment_report ────────────────────────────────────────────────

def export_environment_report(
    environment: dict,
    documents: list[dict],
    graphs: dict[str, dict | None],
) -> str:
    """Generate a full markdown report for an environment.

    Args:
        environment: The environment object from the API.
        documents: List of document search results (with analysisStatus etc.)
        graphs: Dict mapping document_id -> graph_data (or None if no graph).

    Returns:
        Markdown report string.
    """
    env_name = environment.get("name", "Unknown")
    env_id = environment.get("id", "")
    lang = environment.get("llmLanguageTag", "")
    created = environment.get("createdAt", "")[:10]

    total_docs = len(documents)
    success = sum(1 for d in documents if d.get("analysisStatus") == "SUCCESS")
    failed = sum(1 for d in documents if d.get("analysisStatus") == "FAILED")
    pending = total_docs - success - failed
    docs_with_graphs = sum(1 for g in graphs.values() if g and len(g.get("graphData", {}).get("nodes", [])) > 0)

    lines = [
        f"# Environment Report: {env_name}",
        "",
        f"- **ID:** `{env_id}`",
        f"- **Language:** {lang}",
        f"- **Created:** {created}",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total documents | {total_docs} |",
        f"| Analysis SUCCESS | {success} |",
        f"| Analysis FAILED | {failed} |",
        f"| Analysis PENDING | {pending} |",
        f"| Documents with graphs | {docs_with_graphs} |",
        "",
    ]

    if total_docs > 0:
        lines.append(f"**Success rate:** {success / total_docs * 100:.0f}%")
        lines.append("")

    # Metadata schema
    metadata = environment.get("customMetadata", [])
    if metadata:
        lines += [
            "## Metadata Schema",
            "",
            "| Field | Type | Mandatory | Grouped |",
            "|-------|------|-----------|---------|",
        ]
        for m in metadata:
            lines.append(
                f"| {m.get('name', '')} | {m.get('type', '')} "
                f"| {'Yes' if m.get('mandatory') else 'No'} "
                f"| {'Yes' if m.get('grouped') else 'No'} |"
            )
        lines.append("")

    # Document details
    lines += [
        "## Documents",
        "",
        "| # | Document | Analysis | Graph Nodes | Graph Edges |",
        "|---|----------|----------|-------------|-------------|",
    ]

    for i, doc in enumerate(documents, 1):
        doc_obj = doc if "publicName" in doc else doc.get("document", doc)
        name = doc_obj.get("publicName", "?")
        status = doc_obj.get("analysisStatus", "?")
        doc_id = doc_obj.get("id", "")

        g = graphs.get(doc_id)
        if g and "graphData" in g:
            n_nodes = len(g["graphData"].get("nodes", []))
            n_edges = len(g["graphData"].get("edges", []))
        else:
            n_nodes = "–"
            n_edges = "–"

        status_icon = {"SUCCESS": "✅", "FAILED": "❌"}.get(status, "⏳")
        lines.append(f"| {i} | {name} | {status_icon} {status} | {n_nodes} | {n_edges} |")

    lines.append("")

    # Per-document graph summaries
    for doc in documents:
        doc_obj = doc if "publicName" in doc else doc.get("document", doc)
        doc_id = doc_obj.get("id", "")
        doc_name = doc_obj.get("publicName", "?")
        g = graphs.get(doc_id)

        if not g or not g.get("graphData", {}).get("nodes"):
            continue

        gd = g["graphData"]
        g_nodes = gd.get("nodes", [])
        g_edges = gd.get("edges", [])

        lines += [
            f"### {doc_name}",
            "",
            f"- Nodes: {len(g_nodes)}, Edges: {len(g_edges)}, "
            f"Sub-graphs: {g.get('numGraphs', '?')}, Merge: {g.get('mergeMethod', '?')}",
            "",
        ]

        # List nodes
        lines.append("| Node | Label | Causation | Category |")
        lines.append("|------|-------|-----------|----------|")
        for node in sorted(g_nodes, key=lambda n: n.get("nodeId", 0)):
            nid = node.get("nodeId", "?")
            label = _get_node_label(node)
            causation = _get_node_prop(node, "causation") or "–"
            category = _get_node_prop(node, "eventCategory") or "–"
            lines.append(f"| {nid} | {label} | {causation} | {category} |")

        lines += ["", "**Edges:**", ""]
        for edge in g_edges:
            src = edge.get("nodeOriginId")
            dst = edge.get("nodeDestinationId")
            rel = edge.get("relation", "?")
            # Find labels
            src_label = next((_get_node_label(n) for n in g_nodes if n.get("nodeId") == src), str(src))
            dst_label = next((_get_node_label(n) for n in g_nodes if n.get("nodeId") == dst), str(dst))
            lines.append(f"- {src_label} →*{rel}*→ {dst_label}")

        lines += [""]

    lines += [
        "---",
        "*Report generated by Dylogy MCP*",
    ]

    return "\n".join(lines)

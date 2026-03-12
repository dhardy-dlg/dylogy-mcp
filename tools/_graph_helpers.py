"""Shared helpers for graph-related tools."""

from typing import Any


def extract_value(prop: Any) -> Any:
    """Extract the raw value from a graph property dict."""
    if prop is None:
        return None
    if isinstance(prop, dict):
        return prop.get("value")
    return prop


def get_node_label(node: dict) -> str:
    props = node.get("properties", {})
    return extract_value(props.get("label")) or f"Node {node.get('nodeId', '?')}"


def get_node_prop(node: dict, key: str) -> Any:
    return extract_value(node.get("properties", {}).get(key))


def parse_graph(data: dict) -> tuple[list[dict], list[dict], dict]:
    """Extract nodes, edges, properties from a graph API response."""
    gd = data.get("graphData", {})
    return gd.get("nodes", []), gd.get("edges", []), gd.get("properties", {})

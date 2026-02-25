#!/usr/bin/env python3
"""
build_graph.py — Build dependency DAG from enriched JSON and generate DOT format.

Usage:
    python build_graph.py input.json [-o output.json]
"""

import argparse
import json
import sys
from collections import defaultdict, deque


# Node colors by type (Lean Blueprint inspired)
TYPE_COLORS = {
    "definition":   {"fill": "#A3D6FF", "stroke": "#4A90D9", "shape": "box"},
    "theorem":      {"fill": "#FFB3B3", "stroke": "#D94A4A", "shape": "ellipse"},
    "lemma":        {"fill": "#FFDAA3", "stroke": "#D9944A", "shape": "ellipse"},
    "proposition":  {"fill": "#C8B3FF", "stroke": "#7A4AD9", "shape": "ellipse"},
    "corollary":    {"fill": "#B3FFB3", "stroke": "#4AD94A", "shape": "ellipse"},
    "remark":       {"fill": "#E0E0E0", "stroke": "#808080", "shape": "box"},
    "proof":        {"fill": "#F0F0F0", "stroke": "#B0B0B0", "shape": "box"},
    "example":      {"fill": "#FFFFB3", "stroke": "#D9D94A", "shape": "box"},
    "axiom":        {"fill": "#FFB3E6", "stroke": "#D94AB3", "shape": "doubleoctagon"},
    "conjecture":   {"fill": "#FFE0B3", "stroke": "#D9A64A", "shape": "diamond"},
    "notation":     {"fill": "#D0D0D0", "stroke": "#909090", "shape": "box"},
    "assumption":   {"fill": "#FFD0E0", "stroke": "#D96090", "shape": "box"},
    "claim":        {"fill": "#D0FFD0", "stroke": "#60D960", "shape": "ellipse"},
}

# Edge styles by relation
RELATION_STYLES = {
    "references": {"color": "#333333", "style": "solid"},
    "uses":       {"color": "#4A90D9", "style": "solid"},
    "proves":     {"color": "#4AD94A", "style": "dashed"},
    "implicit":   {"color": "#D9944A", "style": "dotted"},
    "cites":      {"color": "#808080", "style": "dotted"},
}


def detect_cycles(adj, nodes):
    """Detect cycles using DFS. Returns list of cycle-forming edges."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    cycle_edges = []

    def dfs(u):
        color[u] = GRAY
        for v in adj.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                cycle_edges.append((u, v))
            elif color[v] == WHITE:
                dfs(v)
        color[u] = BLACK

    for n in nodes:
        if color[n] == WHITE:
            dfs(n)
    return cycle_edges


def topological_sort(adj, nodes):
    """Topological sort using Kahn's algorithm. Returns ordered list and depth map."""
    in_degree = defaultdict(int)
    for n in nodes:
        if n not in in_degree:
            in_degree[n] = 0
    for u in adj:
        for v in adj[u]:
            if v in nodes:
                in_degree[v] += 1

    queue = deque([n for n in nodes if in_degree[n] == 0])
    order = []
    depth = {}

    while queue:
        u = queue.popleft()
        order.append(u)
        depth[u] = 0
        for v in adj.get(u, []):
            if v not in nodes:
                continue
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)
            depth[v] = max(depth.get(v, 0), depth[u] + 1)

    return order, depth


def generate_dot(objects, dependencies, include_proofs=False):
    """Generate Graphviz DOT representation of the dependency graph."""
    obj_map = {o["id"]: o for o in objects}
    lines = ['digraph G {']
    lines.append('  rankdir=BT;')
    lines.append('  node [fontname="Helvetica", fontsize=10];')
    lines.append('  edge [fontsize=8];')
    lines.append('')

    # Add nodes
    for obj in objects:
        if obj["type"] == "proof" and not include_proofs:
            continue
        tc = TYPE_COLORS.get(obj["type"], TYPE_COLORS["remark"])
        label = f"{obj['type'].capitalize()}"
        if obj.get("number"):
            label += f" {obj['number']}"
        if obj.get("title"):
            # Escape quotes and limit length
            title = obj["title"][:50].replace('"', '\\"')
            label += f"\\n{title}"

        node_id = obj["id"].replace(":", "_").replace(".", "_")
        lines.append(
            f'  "{node_id}" ['
            f'label="{label}", '
            f'shape={tc["shape"]}, '
            f'style=filled, '
            f'fillcolor="{tc["fill"]}", '
            f'color="{tc["stroke"]}", '
            f'tooltip="{obj["id"]}"'
            f'];'
        )

    lines.append('')

    # Add edges
    for dep in dependencies:
        from_id = dep["from"]
        to_id = dep["to"]
        if from_id not in obj_map or to_id not in obj_map:
            continue
        if not include_proofs:
            if obj_map[from_id]["type"] == "proof" or obj_map[to_id]["type"] == "proof":
                continue
        rs = RELATION_STYLES.get(dep["relation"], RELATION_STYLES["references"])
        from_node = from_id.replace(":", "_").replace(".", "_")
        to_node = to_id.replace(":", "_").replace(".", "_")
        lines.append(
            f'  "{from_node}" -> "{to_node}" ['
            f'color="{rs["color"]}", '
            f'style={rs["style"]}, '
            f'tooltip="{dep["relation"]}: {dep.get("evidence", "")}"'
            f'];'
        )

    lines.append('}')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Build dependency DAG and generate DOT graph"
    )
    parser.add_argument("input", help="Path to JSON file (from extract or enriched)")
    parser.add_argument("-o", "--output", help="Output JSON file (default: stdout)")
    parser.add_argument("--include-proofs", action="store_true",
                        help="Include proof nodes in the graph")
    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)

    objects = data["objects"]
    dependencies = data.get("dependencies", [])

    # Build adjacency list (from -> [to])
    obj_ids = {o["id"] for o in objects}
    adj = defaultdict(list)
    for dep in dependencies:
        if dep["from"] in obj_ids and dep["to"] in obj_ids:
            adj[dep["from"]].append(dep["to"])

    # Detect cycles
    cycle_edges = detect_cycles(adj, obj_ids)
    if cycle_edges:
        print(f"Warning: {len(cycle_edges)} cycle-forming edges detected:", file=sys.stderr)
        for u, v in cycle_edges:
            print(f"  {u} -> {v}", file=sys.stderr)
        # Remove cycle edges from dependencies
        cycle_set = set(cycle_edges)
        dependencies = [
            d for d in dependencies
            if (d["from"], d["to"]) not in cycle_set
        ]
        # Rebuild adj
        adj = defaultdict(list)
        for dep in dependencies:
            if dep["from"] in obj_ids and dep["to"] in obj_ids:
                adj[dep["from"]].append(dep["to"])

    # Topological sort
    order, depth = topological_sort(adj, obj_ids)

    # Add depth info to objects
    for obj in objects:
        obj["depth"] = depth.get(obj["id"], 0)

    # Generate DOT
    dot = generate_dot(objects, dependencies, include_proofs=args.include_proofs)

    data["dependencies"] = dependencies
    data["dot_graph"] = dot

    output = json.dumps(data, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Built graph: {len(objects)} nodes, {len(dependencies)} edges", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()

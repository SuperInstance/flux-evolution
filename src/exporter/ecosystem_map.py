"""
Ecosystem map generator — produces visual maps of the fleet dependency graph.

Supports Mermaid diagrams, Markdown tables, Graphviz DOT, and ASCII art
representations of the fleet dependency graph, optionally annotated with
health scores.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ------------------------------------------------------------------
# Mermaid map
# ------------------------------------------------------------------

def generate_mermaid_map(
    graph: Any,
    health: Optional[Any] = None,
    title: str = "FLUX Fleet Ecosystem Map",
) -> str:
    """Generate a full ecosystem Mermaid diagram with colour-coded health.

    Parameters
    ----------
    graph : DependencyGraph
        The dependency graph to visualise.
    health : EcosystemHealthReport, optional
        Health report used to colour-code nodes.
    title : str
        Diagram title.
    """
    health_map: Dict[str, float] = {}
    if health and hasattr(health, "repo_healths"):
        for rh in health.repo_healths:
            health_map[rh.name] = rh.health_score

    lines = ["graph TD"]
    lines.append(f'    title "{title}"')

    # Define style classes
    lines.append("")
    lines.append("    classDef critical fill:#ff6b6b,stroke:#c92a2a,color:#fff,stroke-width:2px")
    lines.append("    classDef warning fill:#ffd43b,stroke:#f08c00,color:#000,stroke-width:2px")
    lines.append("    classDef healthy fill:#69db7c,stroke:#2b8a3e,color:#000,stroke-width:2px")
    lines.append("    classDef unknown fill:#dee2e6,stroke:#868e96,color:#000,stroke-width:1px")

    # Add nodes with IDs
    safe_ids: Dict[str, str] = {}
    for repo in sorted(graph.repos):
        sid = repo.replace("/", "__").replace("-", "_").replace(".", "_")
        safe_ids[repo] = sid
        label = repo.split("/")[-1] if "/" in repo else repo
        lines.append(f'    {sid}["{label}"]')

    lines.append("")

    # Edge style map
    _edge_arrows = {
        "uses": "-->",
        "tests": "-.->",
        "implements_spec": "==>",
        "extends": "-->",
        "documents": "-.->",
        "consumes_api": "==>",
        "produces_data": "-->",
    }

    for dep in graph.edges:
        dep_type_val = dep.dep_type.value if hasattr(dep.dep_type, "value") else str(dep.dep_type)
        arrow = _edge_arrows.get(dep_type_val, "-->")
        src_id = safe_ids.get(dep.source_repo, dep.source_repo)
        tgt_id = safe_ids.get(dep.target_repo, dep.target_repo)
        label = dep_type_val.replace("_", " ")
        lines.append(f'    {src_id} {arrow}|{label}| {tgt_id}')

    lines.append("")

    # Apply health-based classes
    for repo, sid in safe_ids.items():
        score = health_map.get(repo, -1)
        if score < 0:
            lines.append(f"    class {sid} unknown")
        elif score < 0.4:
            lines.append(f"    class {sid} critical")
        elif score < 0.65:
            lines.append(f"    class {sid} warning")
        else:
            lines.append(f"    class {sid} healthy")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Markdown map
# ------------------------------------------------------------------

def generate_markdown_map(
    graph: Any,
    health: Optional[Any] = None,
) -> str:
    """Generate a text-based markdown map with status indicators.

    Parameters
    ----------
    graph : DependencyGraph
        The dependency graph to visualise.
    health : EcosystemHealthReport, optional
        Health report for status annotations.
    """
    health_map: Dict[str, float] = {}
    health_details: Dict[str, Any] = {}
    if health and hasattr(health, "repo_healths"):
        for rh in health.repo_healths:
            health_map[rh.name] = rh.health_score
            health_details[rh.name] = rh

    lines: List[str] = []
    lines.append("# Fleet Dependency Map\n")

    # Summary
    lines.append(f"**Repos:** {len(graph.repos)}  ")
    lines.append(f"**Edges:** {len(graph.edges)}\n")

    # Repo health table
    lines.append("## Repo Status\n")
    lines.append("| Repo | Health | Dependencies | Dependents | Status |")
    lines.append("|------|--------|--------------|------------|--------|")

    for repo in sorted(graph.repos):
        score = health_map.get(repo, -1)
        status, indicator = _health_status(score)
        deps = graph.get_dependencies(repo)
        dependents = graph.get_dependents(repo)
        short = repo.split("/")[-1] if "/" in repo else repo
        lines.append(
            f"| {short} | {score:.0%} {indicator} "
            f"| {len(deps)} | {len(dependents)} | {status} |"
        )

    # Dependency edges table
    lines.append("\n## Dependency Edges\n")
    lines.append("| Source | Type | Target | Evidence |")
    lines.append("|--------|------|--------|----------|")

    for dep in graph.edges:
        dep_type = dep.dep_type.value if hasattr(dep.dep_type, "value") else str(dep.dep_type)
        src_short = dep.source_repo.split("/")[-1] if "/" in dep.source_repo else dep.source_repo
        tgt_short = dep.target_repo.split("/")[-1] if "/" in dep.target_repo else dep.target_repo
        evidence = ", ".join(dep.evidence[:3]) if dep.evidence else "-"
        lines.append(f"| {src_short} | {dep_type} | {tgt_short} | {evidence} |")

    # Critical path
    critical = graph.get_critical_path()
    if critical:
        lines.append(f"\n## Critical Path\n")
        lines.append(f"Repos that everything else depends on: **{', '.join(critical)}**")

    # Orphans
    orphans = graph.get_orphan_repos()
    if orphans:
        lines.append(f"\n## Orphan Repos\n")
        lines.append(f"Repos with no dependencies: {', '.join(orphans)}")

    lines.append("\n---\n*Generated by flux-evolution.*")
    return "\n".join(lines)


# ------------------------------------------------------------------
# DOT (Graphviz) map
# ------------------------------------------------------------------

def generate_dot_map(
    graph: Any,
    health: Optional[Any] = None,
) -> str:
    """Generate a Graphviz DOT format representation.

    Parameters
    ----------
    graph : DependencyGraph
        The dependency graph to visualise.
    health : EcosystemHealthReport, optional
        Health report for node colouring.
    """
    health_map: Dict[str, float] = {}
    if health and hasattr(health, "repo_healths"):
        for rh in health.repo_healths:
            health_map[rh.name] = rh.health_score

    lines: List[str] = []
    lines.append('digraph fleet {')
    lines.append('    rankdir=LR;')
    lines.append('    fontname="Helvetica";')
    lines.append('    node [shape=box, fontname="Helvetica", style=filled];')
    lines.append('')

    # Nodes
    for repo in sorted(graph.repos):
        short = repo.split("/")[-1] if "/" in repo else repo
        score = health_map.get(repo, -1)
        colour = _dot_colour(score)
        lines.append(f'    "{short}" [fillcolor="{colour}"];')

    lines.append("")

    # Edges
    _edge_styles = {
        "uses": '[color="#4263eb"]',
        "tests": '[color="#ae3ec9", style=dashed]',
        "implements_spec": '[color="#2b8a3e", style=bold]',
        "extends": '[color="#e67700"]',
        "documents": '[color="#868e96", style=dashed]',
        "consumes_api": '[color="#1098ad", style=bold]',
        "produces_data": '[color="#d6336c"]',
    }

    for dep in graph.edges:
        dep_type_val = dep.dep_type.value if hasattr(dep.dep_type, "value") else str(dep.dep_type)
        src_short = dep.source_repo.split("/")[-1] if "/" in dep.source_repo else dep.source_repo
        tgt_short = dep.target_repo.split("/")[-1] if "/" in dep.target_repo else dep.target_repo
        style = _edge_styles.get(dep_type_val, "")
        lines.append(f'    "{src_short}" -> "{tgt_short}" {style};')

    lines.append('}')
    return "\n".join(lines)


# ------------------------------------------------------------------
# ASCII map
# ------------------------------------------------------------------

def generate_ascii_map(
    graph: Any,
    health: Optional[Any] = None,
    width: int = 72,
) -> str:
    """Generate a terminal-friendly ASCII art map of the dependency graph.

    Parameters
    ----------
    graph : DependencyGraph
        The dependency graph to visualise.
    health : EcosystemHealthReport, optional
        Health report for status indicators.
    width : int
        Maximum line width for the ASCII output.
    """
    health_map: Dict[str, float] = {}
    if health and hasattr(health, "repo_healths"):
        for rh in health.repo_healths:
            health_map[rh.name] = rh.health_score

    lines: List[str] = []
    sep = "=" * width
    thin = "-" * width

    lines.append(sep)
    lines.append("  FLUX FLEET DEPENDENCY MAP".center(width))
    lines.append(f"  {len(graph.repos)} repos  |  {len(graph.edges)} dependencies".center(width))
    lines.append(sep)

    # Group repos by dependency depth (topological layers)
    try:
        topo = graph.topological_sort()
    except ValueError:
        topo = sorted(graph.repos)

    # Compute layers via BFS from the topological order
    layers: Dict[str, int] = {}
    in_degree: Dict[str, int] = {r: 0 for r in graph.repos}
    adj: Dict[str, List[str]] = {r: [] for r in graph.repos}

    for dep in graph.edges:
        src, tgt = dep.source_repo, dep.target_repo
        if tgt in adj:
            adj[src].append(tgt) if src in adj else None
            in_degree[tgt] = in_degree.get(tgt, 0) + 1

    # Simple layer assignment
    for node in topo:
        max_parent_layer = -1
        for dep in graph.get_dependents(node):
            parent = dep.source_repo
            if parent in layers:
                max_parent_layer = max(max_parent_layer, layers[parent])
        layers[node] = max_parent_layer + 1

    # Group by layer
    layer_groups: Dict[int, List[str]] = {}
    for repo, layer in layers.items():
        layer_groups.setdefault(layer, []).append(repo)

    # Draw layers
    for layer_num in sorted(layer_groups.keys()):
        repos = layer_groups[layer_num]
        lines.append("")
        lines.append(thin)
        layer_label = f"  LAYER {layer_num}".ljust(width // 2)
        if layer_num == 0:
            layer_label += "Foundational"
        elif layer_num == max(layer_groups.keys()):
            layer_label += "Leaf / Consumer"
        else:
            layer_label += "Intermediate"
        lines.append(layer_label)
        lines.append(thin)

        for repo in sorted(repos):
            short = repo.split("/")[-1] if "/" in repo else repo
            score = health_map.get(repo, -1)
            bar = _ascii_health_bar(score)
            deps_out = graph.get_dependencies(repo)
            deps_in = graph.get_dependents(repo)

            status_indicator = ""
            if score >= 0.65:
                status_indicator = "[OK]"
            elif score >= 0.4:
                status_indicator = "[~~]"
            elif score >= 0:
                status_indicator = "[!!]"
            else:
                status_indicator = "[??]"

            line = f"  {status_indicator} {short}"
            if bar:
                line += f"  {bar}"
            lines.append(line)

            # Show dependencies (indented)
            for dep in deps_out[:4]:
                tgt_short = dep.target_repo.split("/")[-1] if "/" in dep.target_repo else dep.target_repo
                dep_type = dep.dep_type.value if hasattr(dep.dep_type, "value") else str(dep.dep_type)
                lines.append(f"       -> {tgt_short} ({dep_type})")
            if len(deps_out) > 4:
                lines.append(f"       ... +{len(deps_out) - 4} more")

    # Summary footer
    lines.append("")
    lines.append(sep)
    critical = graph.get_critical_path()
    if critical:
        lines.append(f"  CRITICAL PATH: {', '.join(critical)}")
    orphans = graph.get_orphan_repos()
    if orphans:
        lines.append(f"  ORPHANS: {', '.join(orphans)}")
    cycles = graph.get_cycles()
    if cycles:
        lines.append(f"  CYCLES DETECTED: {len(cycles)}")
        for cycle in cycles[:3]:
            lines.append(f"    {' -> '.join(cycle)} -> (loop)")
    lines.append(sep)

    # Legend
    lines.append("")
    lines.append("  Legend:")
    lines.append("  [OK]  Health >= 65%  |  [~~] 40-65%  |  [!!] < 40%  |  [??] Unknown")
    lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _health_status(score: float) -> Tuple[str, str]:
    """Return (status_text, emoji_indicator) for a health score."""
    if score < 0:
        return "Unknown", "\u2753"
    elif score < 0.4:
        return "Critical", "\U0001f534"
    elif score < 0.65:
        return "Warning", "\U0001f7e1"
    else:
        return "Healthy", "\U0001f7e2"


def _health_bar(score: float) -> str:
    """Return a small text health bar."""
    if score < 0:
        return ""
    filled = int(score * 5)
    empty = 5 - filled
    return "[" + "#" * filled + "-" * empty + "]"


def _dot_colour(score: float) -> str:
    """Return a hex colour for DOT node fill."""
    if score < 0:
        return "#dee2e6"
    elif score < 0.4:
        # Red
        r, g, b = 255, int(107 * score / 0.4), int(107 * score / 0.4)
        return f"#{r:02x}{g:02x}{b:02x}"
    elif score < 0.65:
        # Yellow/orange
        t = (score - 0.4) / 0.25
        r, g, b = 255, int(180 + 30 * t), int(59 * t)
        return f"#{r:02x}{g:02x}{b:02x}"
    else:
        # Green
        t = (score - 0.65) / 0.35
        r, g, b = int(105 - 40 * t), int(219 + 10 * t), int(124 - 30 * t)
        return f"#{r:02x}{g:02x}{b:02x}"


def _ascii_health_bar(score: float) -> str:
    """Return an ASCII health bar for terminal display."""
    if score < 0:
        return "[????]"
    filled = int(score * 8)
    empty = 8 - filled
    return "[" + "\u2588" * filled + "\u2591" * empty + "]"

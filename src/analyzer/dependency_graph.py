"""
Fleet dependency graph — models and analyzes inter-repo relationships.

Tracks how repos USE, TEST, IMPLEMENT_SPEC, EXTEND, DOCUMENT, CONSUME_API,
and PRODUCE_DATA relative to each other.  Provides cycle detection, topological
ordering, impact analysis, and serialisation to Mermaid / JSON formats.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


# ------------------------------------------------------------------
# Enums & data classes
# ------------------------------------------------------------------

class DependencyType(Enum):
    """Semantics of an inter-repo dependency edge."""
    USES = "uses"
    TESTS = "tests"
    IMPLEMENTS_SPEC = "implements_spec"
    EXTENDS = "extends"
    DOCUMENTS = "documents"
    CONSUMES_API = "consumes_api"
    PRODUCES_DATA = "produces_data"


@dataclass
class Dependency:
    """A single directed dependency edge between two repos."""
    source_repo: str
    target_repo: str
    dep_type: DependencyType
    description: str = ""
    evidence: List[str] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash((self.source_repo, self.target_repo, self.dep_type))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Dependency):
            return NotImplemented
        return (
            self.source_repo == other.source_repo
            and self.target_repo == other.target_repo
            and self.dep_type == other.dep_type
        )


# ------------------------------------------------------------------
# Core graph
# ------------------------------------------------------------------

class DependencyGraph:
    """Directed graph of fleet-wide inter-repo dependencies.

    Edges are ``Dependency`` objects so multiple typed edges can exist
    between the same pair of repos (e.g. A *uses* B and A *tests* B).
    """

    def __init__(self) -> None:
        # source -> set of Dependencies
        self._edges: Dict[str, Set[Dependency]] = defaultdict(set)
        self._repos: Set[str] = set()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_dependency(self, dep: Dependency) -> None:
        """Add a dependency edge to the graph."""
        self._edges[dep.source_repo].add(dep)
        self._repos.add(dep.source_repo)
        self._repos.add(dep.target_repo)

    def remove_dependency(self, source: str, target: str) -> int:
        """Remove all edges from *source* to *target*.  Returns count removed."""
        if source not in self._edges:
            return 0
        before = len(self._edges[source])
        self._edges[source] = {
            d for d in self._edges[source] if d.target_repo != target
        }
        removed = before - len(self._edges[source])
        if not self._edges[source]:
            del self._edges[source]
        return removed

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_dependencies(self, repo: str) -> List[Dependency]:
        """Return all edges where *repo* is the source (outgoing)."""
        return sorted(self._edges.get(repo, set()), key=lambda d: d.target_repo)

    def get_dependents(self, repo: str) -> List[Dependency]:
        """Return all edges where *repo* is the target (incoming)."""
        result: List[Dependency] = []
        for src, edges in self._edges.items():
            for dep in edges:
                if dep.target_repo == repo:
                    result.append(dep)
        return sorted(result, key=lambda d: d.source_repo)

    @property
    def repos(self) -> FrozenSet[str]:
        """All repos that appear in the graph."""
        return frozenset(self._repos)

    @property
    def edges(self) -> List[Dependency]:
        """All edges in the graph."""
        all_deps: List[Dependency] = []
        for edges in self._edges.values():
            all_deps.extend(edges)
        return all_deps

    def get_critical_path(self) -> List[str]:
        """Repos that everything else (transitively) depends on.

        These are the "leaf" nodes — they have no outgoing edges but
        at least one incoming edge.  Typically specs and foundational
        libraries live here.
        """
        has_outgoing: Set[str] = set()
        has_incoming: Set[str] = set()

        for src, edges in self._edges.items():
            has_outgoing.add(src)
            for dep in edges:
                has_incoming.add(dep.target_repo)

        # Critical = has dependents but no dependencies of its own
        critical = has_incoming - has_outgoing
        return sorted(critical)

    def get_orphan_repos(self) -> List[str]:
        """Repos with no incoming *and* no outgoing edges."""
        connected: Set[str] = set()
        for src, edges in self._edges.items():
            connected.add(src)
            for dep in edges:
                connected.add(dep.target_repo)

        orphans = self._repos - connected
        # Actually, a repo that appears only as a target/source with
        # edges is not an orphan.  Orphans are repos registered but
        # never connected.
        return sorted(orphans)

    def get_cycles(self) -> List[List[str]]:
        """Detect circular dependency chains.

        Returns a list of cycles, each cycle being a list of repo names
        forming the loop.  Uses DFS with three-colour marking (white /
        gray / black) for efficient detection on large graphs.
        """
        # Build simple adjacency for cycle detection (ignore edge types)
        adj: Dict[str, Set[str]] = defaultdict(set)
        for src, edges in self._edges.items():
            for dep in edges:
                adj[src].add(dep.target_repo)

        WHITE, GRAY, BLACK = 0, 1, 2
        colour: Dict[str, int] = {r: WHITE for r in self._repos}
        path: List[str] = []
        path_set: Set[str] = set()
        cycles: List[List[str]] = []
        found_cycles: Set[Tuple[str, ...]] = set()  # deduplicate

        def _dfs(node: str) -> None:
            colour[node] = GRAY
            path.append(node)
            path_set.add(node)

            for neighbour in sorted(adj.get(node, set())):
                if colour.get(neighbour) == GRAY:
                    # Back edge — cycle found
                    cycle_start = path.index(neighbour)
                    cycle = path[cycle_start:]
                    key = tuple(cycle)
                    if key not in found_cycles:
                        found_cycles.add(key)
                        cycles.append(list(cycle))
                elif colour.get(neighbour, WHITE) == WHITE:
                    _dfs(neighbour)

            path.pop()
            path_set.discard(node)
            colour[node] = BLACK

        for node in sorted(self._repos):
            if colour.get(node, WHITE) == WHITE:
                _dfs(node)

        return cycles

    def topological_sort(self) -> List[str]:
        """Return repos in build / evaluation order.

        Dependencies (targets) come before dependents (sources), so
        changing any repo only affects repos that appear later.

        Raises ``ValueError`` if the graph contains cycles.
        """
        # Reverse edges: target -> source so dependencies come first.
        # Edge source depends on target, so target should be built first.
        adj: Dict[str, Set[str]] = defaultdict(set)
        in_degree: Dict[str, int] = {r: 0 for r in self._repos}

        for src, edges in self._edges.items():
            for dep in edges:
                target = dep.target_repo
                # Reverse: target -> source (build dependency first)
                if src not in adj[target]:
                    adj[target].add(src)
                    in_degree[src] = in_degree.get(src, 0) + 1

        queue: deque[str] = deque(
            sorted(r for r, deg in in_degree.items() if deg == 0)
        )
        result: List[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbour in sorted(adj.get(node, set())):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if len(result) != len(self._repos):
            raise ValueError(
                "Graph contains cycles; cannot topologically sort. "
                "Use get_cycles() to identify circular dependencies."
            )

        return result

    def compute_impact(self, repo: str) -> Dict[str, Any]:
        """If *repo* changes, how many repos are affected?

        Returns a dict with:
        - ``direct_dependents``: repos that directly depend on *repo*
        - ``total_affected``: count including transitive dependents
        - ``affected_repos``: ordered list of all transitively affected repos
        - ``max_depth``: longest dependency chain from *repo* to a leaf
        """
        # BFS from repo following reverse edges
        adj: Dict[str, Set[str]] = defaultdict(set)
        for src, edges in self._edges.items():
            for dep in edges:
                adj[dep.target_repo].add(src)  # reverse: target -> source

        direct = sorted(adj.get(repo, set()))
        visited: Set[str] = {repo}
        affected: List[str] = []
        queue: deque[Tuple[str, int]] = deque((r, 1) for r in direct)

        max_depth = 0
        while queue:
            node, depth = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            affected.append(node)
            max_depth = max(max_depth, depth)
            for neighbour in adj.get(node, set()):
                if neighbour not in visited:
                    queue.append((neighbour, depth + 1))

        return {
            "repo": repo,
            "direct_dependents": direct,
            "total_affected": len(affected),
            "affected_repos": affected,
            "max_depth": max_depth,
        }

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_mermaid(self, title: str = "Fleet Dependency Graph") -> str:
        """Generate a Mermaid flowchart diagram of the graph."""
        lines = [f"graph TD"]
        lines.append(f"    title {title}")

        # Colour-code by dep type
        style_map = {
            DependencyType.USES: "uses",
            DependencyType.TESTS: "tests",
            DependencyType.IMPLEMENTS_SPEC: "impl",
            DependencyType.EXTENDS: "extends",
            DependencyType.DOCUMENTS: "docs",
            DependencyType.CONSUMES_API: "api",
            DependencyType.PRODUCES_DATA: "data",
        }

        edge_type_styles: Dict[str, str] = {
            "uses": ">",
            "tests": "-.->",
            "impl": "==>",
            "extends": "-->",
            "docs": "-.->",
            "api": "==>",
            "data": "-->",
        }

        for dep in self.edges:
            arrow = edge_type_styles.get(style_map.get(dep.dep_type, "uses"), ">")
            safe_src = dep.source_repo.replace("/", "_").replace("-", "_")
            safe_tgt = dep.target_repo.replace("/", "_").replace("-", "_")
            label = dep.dep_type.value.replace("_", " ")
            lines.append(
                f'    {safe_src} {arrow}|{label}| {safe_tgt}'
            )

        return "\n".join(lines)

    def to_json(self) -> Dict[str, Any]:
        """Serialise the graph for visualisation tools."""
        nodes: List[Dict[str, str]] = []
        edges_json: List[Dict[str, Any]] = []

        for repo in sorted(self._repos):
            nodes.append({"id": repo, "label": repo})

        for dep in self.edges:
            edges_json.append({
                "source": dep.source_repo,
                "target": dep.target_repo,
                "type": dep.dep_type.value,
                "description": dep.description,
                "evidence": dep.evidence,
            })

        return {
            "nodes": nodes,
            "edges": edges_json,
            "meta": {
                "total_repos": len(nodes),
                "total_edges": len(edges_json),
            },
        }

    # ------------------------------------------------------------------
    # Factory — auto-detect from fleet repos
    # ------------------------------------------------------------------

    @classmethod
    def from_fleet_repos(
        cls,
        repo_roots: Optional[Dict[str, str]] = None,
        file_contents: Optional[Dict[str, Dict[str, str]]] = None,
        issue_references: Optional[Dict[str, List[str]]] = None,
    ) -> "DependencyGraph":
        """Auto-detect dependencies by scanning import statements,
        file references, and issue cross-references across repos.

        Parameters
        ----------
        repo_roots : dict, optional
            Mapping of repo name -> filesystem root path.
        file_contents : dict, optional
            Mapping of repo name -> {file_path: content_string}.
            Used when filesystem scanning is not available.
        issue_references : dict, optional
            Mapping of repo name -> list of referenced repo names
            extracted from issues / PR descriptions.
        """
        graph = cls()

        # ---- Strategy 1: scan file contents for import / require patterns
        if file_contents:
            for repo, files in file_contents.items():
                for fpath, content in files.items():
                    _scan_content(repo, fpath, content, graph)

        # ---- Strategy 2: scan filesystem directories
        if repo_roots:
            import os

            for repo, root in repo_roots.items():
                if not os.path.isdir(root):
                    continue
                for dirpath, dirnames, filenames in os.walk(root):
                    # Skip hidden dirs and common non-source dirs
                    dirnames[:] = [
                        d for d in dirnames
                        if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git")
                    ]
                    for fname in filenames:
                        if fname.endswith((".py", ".ts", ".js", ".rs", ".go", ".toml", ".json")):
                            fpath = os.path.join(dirpath, fname)
                            try:
                                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                    content = f.read()
                                _scan_content(repo, fpath, content, graph)
                            except OSError:
                                continue

        # ---- Strategy 3: explicit issue cross-references
        if issue_references:
            for repo, referenced in issue_references.items():
                for ref_repo in referenced:
                    if ref_repo != repo:
                        graph.add_dependency(Dependency(
                            source_repo=repo,
                            target_repo=ref_repo,
                            dep_type=DependencyType.USES,
                            description=f"Referenced in issues/PRs",
                            evidence=[f"issue-reference:{ref_repo}"],
                        ))

        return graph


# ------------------------------------------------------------------
# Content scanning helpers
# ------------------------------------------------------------------

# Patterns that suggest inter-repo dependencies
_IMPORT_PATTERNS = [
    "from flux-", "import flux-",
    "from flux_", "import flux_",
    'require("flux-', 'require("flux_',
    "use flux-", "use flux_",
]

_SPEC_PATTERNS = [
    "implements spec", "implements the spec", "per spec",
    "conformance", "spec compliance",
]

_TEST_PATTERNS = [
    "test(", "describe(", "it(", "#[test]",
    "conformance test", "test suite for",
]

_DOC_PATTERNS = [
    "see also:", "docs for", "documentation for",
    "ref: ", "related: ",
]


def _extract_repo_names(text: str) -> List[str]:
    """Extract flux-* and flux_* repo name mentions from text."""
    import re
    # Match both flux-xxx and flux_xxx patterns
    pattern = r"flux[-_][a-zA-Z0-9_-]+"
    matches = re.findall(pattern, text)
    # Normalise underscores to hyphens for consistency
    matches = [m.replace("_", "-") for m in matches]
    return list(set(matches))


def _scan_content(
    repo: str,
    fpath: str,
    content: str,
    graph: DependencyGraph,
) -> None:
    """Scan a single file for dependency signals and add edges."""
    content_lower = content.lower()

    mentioned_repos = _extract_repo_names(content_lower)
    mentioned_repos = [r for r in mentioned_repos if r != repo and f"flux-" in r]

    if not mentioned_repos:
        return

    # Determine dependency type based on file content
    for mentioned in mentioned_repos:
        dep_type = DependencyType.USES
        desc_parts: List[str] = []

        if fpath.endswith(".toml"):
            dep_type = DependencyType.USES
            desc_parts.append("build dependency")
        elif fpath.endswith(".json"):
            dep_type = DependencyType.CONSUMES_API
            desc_parts.append("API dependency")
        elif fpath.startswith(("test/", "tests/", "__tests__/")) or "test" in fpath:
            dep_type = DependencyType.TESTS
            desc_parts.append("test target")
        elif any(p in content_lower for p in _SPEC_PATTERNS):
            dep_type = DependencyType.IMPLEMENTS_SPEC
            desc_parts.append("spec implementation")
        elif any(p in content_lower for p in _DOC_PATTERNS):
            dep_type = DependencyType.DOCUMENTS
            desc_parts.append("documentation reference")
        elif any(p in content_lower for p in _IMPORT_PATTERNS):
            dep_type = DependencyType.USES
            desc_parts.append("code import")
        elif "produce" in content_lower or "output" in content_lower or "emit" in content_lower:
            dep_type = DependencyType.PRODUCES_DATA
            desc_parts.append("data producer")

        graph.add_dependency(Dependency(
            source_repo=repo,
            target_repo=mentioned,
            dep_type=dep_type,
            description=f"{repo} {dep_type.value} {mentioned}: {', '.join(desc_parts)}",
            evidence=[fpath],
        ))

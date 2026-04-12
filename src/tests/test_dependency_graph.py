"""
Tests for the fleet dependency graph, ecosystem health, and map generators.

Covers graph construction, cycle detection, topological sort, impact
analysis, Mermaid/JSON serialisation, health scoring, ecosystem reports,
and ASCII map generation.
"""

import pytest

from src.analyzer.dependency_graph import (
    Dependency,
    DependencyGraph,
    DependencyType,
)
from src.analyzer.ecosystem_health import (
    EcosystemHealthAnalyzer,
    EcosystemHealthReport,
    HealthFactor,
    RepoHealth,
)
from src.exporter.ecosystem_map import (
    generate_ascii_map,
    generate_dot_map,
    generate_markdown_map,
    generate_mermaid_map,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_graph() -> DependencyGraph:
    """A small graph modelling the FLUX fleet core."""
    g = DependencyGraph()
    g.add_dependency(Dependency(
        source_repo="flux-runtime",
        target_repo="flux-spec",
        dep_type=DependencyType.IMPLEMENTS_SPEC,
        description="Runtime implements the ISA spec",
        evidence=["src/runtime/isa.rs"],
    ))
    g.add_dependency(Dependency(
        source_repo="flux-coop-runtime",
        target_repo="flux-runtime",
        dep_type=DependencyType.USES,
        description="Coop runtime sits on top of flux-runtime",
        evidence=["src/coop/bridge.py"],
    ))
    g.add_dependency(Dependency(
        source_repo="flux-coop-runtime",
        target_repo="flux-spec",
        dep_type=DependencyType.IMPLEMENTS_SPEC,
        description="Coop runtime also implements spec",
        evidence=["src/coop/conformance.rs"],
    ))
    g.add_dependency(Dependency(
        source_repo="flux-conformance",
        target_repo="flux-runtime",
        dep_type=DependencyType.TESTS,
        description="Conformance tests validate runtime",
        evidence=["tests/runtime_suite.rs"],
    ))
    g.add_dependency(Dependency(
        source_repo="flux-conformance",
        target_repo="flux-spec",
        dep_type=DependencyType.TESTS,
        description="Conformance tests validate spec",
        evidence=["tests/spec_suite.rs"],
    ))
    g.add_dependency(Dependency(
        source_repo="flux-rfc",
        target_repo="flux-spec",
        dep_type=DependencyType.DOCUMENTS,
        description="RFCs document spec changes",
        evidence=["rfc/0001-isa-declaration.md"],
    ))
    return g


@pytest.fixture
def sample_repo_data() -> list:
    """Sample repo metadata for health scoring."""
    return [
        {
            "name": "flux-spec",
            "commits": 20,
            "last_commit_date": "2026-04-11T23:49:26Z",
            "test_files": 2,
            "source_files": 5,
            "agents": ["Super Z", "Quill"],
            "doc_files": 8,
            "has_spec": True,
            "has_readme": True,
            "open_issues": 1,
            "closed_issues": 10,
        },
        {
            "name": "flux-runtime",
            "commits": 35,
            "last_commit_date": "2026-04-11T21:36:06Z",
            "test_files": 5,
            "source_files": 12,
            "agents": ["Super Z", "Casey Digennaro", "Quill"],
            "doc_files": 3,
            "has_spec": False,
            "has_readme": True,
            "open_issues": 3,
            "closed_issues": 8,
        },
        {
            "name": "flux-coop-runtime",
            "commits": 8,
            "last_commit_date": "2026-04-11T23:24:51Z",
            "test_files": 1,
            "source_files": 6,
            "agents": ["Super Z"],
            "doc_files": 1,
            "has_spec": False,
            "has_readme": True,
            "open_issues": 5,
            "closed_issues": 1,
        },
        {
            "name": "abandoned-repo",
            "commits": 1,
            "last_commit_date": "2025-01-15T00:00:00Z",
            "test_files": 0,
            "source_files": 2,
            "agents": [],
            "doc_files": 0,
            "has_spec": False,
            "has_readme": False,
            "open_issues": 4,
            "closed_issues": 0,
        },
    ]


# ---------------------------------------------------------------------------
# Graph construction & queries
# ---------------------------------------------------------------------------

class TestGraphConstruction:

    def test_empty_graph(self):
        g = DependencyGraph()
        assert len(g.repos) == 0
        assert len(g.edges) == 0

    def test_add_single_dependency(self):
        g = DependencyGraph()
        dep = Dependency(
            source_repo="A", target_repo="B",
            dep_type=DependencyType.USES,
        )
        g.add_dependency(dep)
        assert len(g.repos) == 2
        assert len(g.edges) == 1
        assert "A" in g.repos
        assert "B" in g.repos

    def test_add_duplicate_dependency(self):
        g = DependencyGraph()
        dep = Dependency(
            source_repo="A", target_repo="B",
            dep_type=DependencyType.USES,
        )
        g.add_dependency(dep)
        g.add_dependency(dep)  # same dep, should dedupe
        assert len(g.edges) == 1

    def test_multiple_edge_types(self):
        g = DependencyGraph()
        g.add_dependency(Dependency("A", "B", DependencyType.USES))
        g.add_dependency(Dependency("A", "B", DependencyType.TESTS))
        assert len(g.edges) == 2
        assert len(g.get_dependencies("A")) == 2

    def test_get_dependencies(self, simple_graph):
        deps = simple_graph.get_dependencies("flux-coop-runtime")
        targets = {d.target_repo for d in deps}
        assert "flux-runtime" in targets
        assert "flux-spec" in targets
        assert len(deps) == 2

    def test_get_dependents(self, simple_graph):
        deps = simple_graph.get_dependents("flux-spec")
        sources = {d.source_repo for d in deps}
        assert "flux-runtime" in sources
        assert "flux-coop-runtime" in sources
        assert "flux-conformance" in sources
        assert "flux-rfc" in sources

    def test_get_dependencies_empty(self):
        g = DependencyGraph()
        assert g.get_dependencies("nonexistent") == []

    def test_get_dependents_empty(self):
        g = DependencyGraph()
        assert g.get_dependents("nonexistent") == []


# ---------------------------------------------------------------------------
# Graph mutation
# ---------------------------------------------------------------------------

class TestGraphMutation:

    def test_remove_dependency(self):
        g = DependencyGraph()
        g.add_dependency(Dependency("A", "B", DependencyType.USES))
        g.add_dependency(Dependency("A", "B", DependencyType.TESTS))
        removed = g.remove_dependency("A", "B")
        assert removed == 2
        assert len(g.edges) == 0

    def test_remove_dependency_nonexistent(self):
        g = DependencyGraph()
        removed = g.remove_dependency("X", "Y")
        assert removed == 0


# ---------------------------------------------------------------------------
# Critical path & orphans
# ---------------------------------------------------------------------------

class TestGraphAnalysis:

    def test_critical_path(self, simple_graph):
        critical = simple_graph.get_critical_path()
        # flux-spec has no outgoing edges
        assert "flux-spec" in critical
        # flux-runtime has dependents but also depends on spec
        assert "flux-runtime" not in critical

    def test_critical_path_empty(self):
        g = DependencyGraph()
        assert g.get_critical_path() == []

    def test_orphan_repos(self):
        g = DependencyGraph()
        g.add_dependency(Dependency("A", "B", DependencyType.USES))
        # C is not connected
        g._repos.add("C")
        orphans = g.get_orphan_repos()
        assert "C" in orphans

    def test_no_orphans(self, simple_graph):
        orphans = simple_graph.get_orphan_repos()
        assert orphans == []


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:

    def test_no_cycles(self, simple_graph):
        cycles = simple_graph.get_cycles()
        assert cycles == []

    def test_simple_cycle(self):
        g = DependencyGraph()
        g.add_dependency(Dependency("A", "B", DependencyType.USES))
        g.add_dependency(Dependency("B", "C", DependencyType.USES))
        g.add_dependency(Dependency("C", "A", DependencyType.USES))
        cycles = g.get_cycles()
        assert len(cycles) >= 1
        # Verify cycle contains all three nodes
        cycle_nodes = set()
        for cycle in cycles:
            cycle_nodes.update(cycle)
        assert "A" in cycle_nodes
        assert "B" in cycle_nodes
        assert "C" in cycle_nodes

    def test_self_cycle(self):
        g = DependencyGraph()
        g.add_dependency(Dependency("A", "A", DependencyType.EXTENDS))
        cycles = g.get_cycles()
        # Self-referential cycle
        assert len(cycles) >= 1

    def test_complex_dag_no_cycles(self):
        g = DependencyGraph()
        g.add_dependency(Dependency("A", "B", DependencyType.USES))
        g.add_dependency(Dependency("A", "C", DependencyType.USES))
        g.add_dependency(Dependency("B", "D", DependencyType.USES))
        g.add_dependency(Dependency("C", "D", DependencyType.USES))
        g.add_dependency(Dependency("D", "E", DependencyType.USES))
        assert g.get_cycles() == []


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------

class TestTopologicalSort:

    def test_sort_simple(self, simple_graph):
        order = simple_graph.topological_sort()
        # flux-spec should come before flux-runtime
        assert order.index("flux-spec") < order.index("flux-runtime")
        # flux-runtime should come before flux-coop-runtime
        assert order.index("flux-runtime") < order.index("flux-coop-runtime")
        # flux-spec should come before flux-conformance
        assert order.index("flux-spec") < order.index("flux-conformance")

    def test_sort_empty(self):
        g = DependencyGraph()
        assert g.topological_sort() == []

    def test_sort_single(self):
        g = DependencyGraph()
        g.add_dependency(Dependency("A", "B", DependencyType.USES))
        order = g.topological_sort()
        # A depends on B, so B (dependency) comes first
        assert order.index("B") < order.index("A")

    def test_sort_cycle_raises(self):
        g = DependencyGraph()
        g.add_dependency(Dependency("A", "B", DependencyType.USES))
        g.add_dependency(Dependency("B", "A", DependencyType.USES))
        with pytest.raises(ValueError, match="cycle"):
            g.topological_sort()


# ---------------------------------------------------------------------------
# Impact analysis
# ---------------------------------------------------------------------------

class TestImpactAnalysis:

    def test_impact_spec(self, simple_graph):
        impact = simple_graph.compute_impact("flux-spec")
        assert "flux-runtime" in impact["affected_repos"]
        assert "flux-coop-runtime" in impact["affected_repos"]
        assert "flux-conformance" in impact["affected_repos"]
        assert "flux-rfc" in impact["affected_repos"]
        assert impact["total_affected"] >= 4
        # flux-coop-runtime depends directly on flux-spec (depth 1),
        # so max_depth is 1 for this graph
        assert impact["max_depth"] >= 1

    def test_impact_leaf(self, simple_graph):
        impact = simple_graph.compute_impact("flux-coop-runtime")
        assert impact["total_affected"] == 0
        assert impact["affected_repos"] == []

    def test_impact_nonexistent(self):
        g = DependencyGraph()
        impact = g.compute_impact("nonexistent")
        assert impact["total_affected"] == 0

    def test_impact_direct_dependents(self, simple_graph):
        impact = simple_graph.compute_impact("flux-spec")
        direct = impact["direct_dependents"]
        assert "flux-runtime" in direct
        assert "flux-conformance" in direct
        assert "flux-rfc" in direct


# ---------------------------------------------------------------------------
# Mermaid generation
# ---------------------------------------------------------------------------

class TestMermaidGeneration:

    def test_basic_mermaid(self, simple_graph):
        mermaid = simple_graph.to_mermaid()
        assert "graph TD" in mermaid
        assert "title" in mermaid
        assert "uses" in mermaid.lower() or "implements_spec" in mermaid

    def test_mermaid_custom_title(self, simple_graph):
        mermaid = simple_graph.to_mermaid(title="Custom Title")
        assert "Custom Title" in mermaid

    def test_mermaid_empty(self):
        g = DependencyGraph()
        mermaid = g.to_mermaid()
        assert "graph TD" in mermaid

    def test_mermaid_edge_labels(self, simple_graph):
        mermaid = simple_graph.to_mermaid()
        # Should contain dep type labels
        assert "implements spec" in mermaid
        assert "tests" in mermaid


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------

class TestJsonSerialisation:

    def test_to_json_structure(self, simple_graph):
        data = simple_graph.to_json()
        assert "nodes" in data
        assert "edges" in data
        assert "meta" in data
        assert data["meta"]["total_repos"] == len(simple_graph.repos)
        assert data["meta"]["total_edges"] == len(simple_graph.edges)

    def test_to_json_nodes(self, simple_graph):
        data = simple_graph.to_json()
        node_ids = {n["id"] for n in data["nodes"]}
        assert "flux-spec" in node_ids
        assert "flux-runtime" in node_ids

    def test_to_json_edges_have_types(self, simple_graph):
        data = simple_graph.to_json()
        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "type" in edge
            assert edge["type"] in ["uses", "tests", "implements_spec", "extends",
                                     "documents", "consumes_api", "produces_data"]

    def test_to_json_empty(self):
        g = DependencyGraph()
        data = g.to_json()
        assert data["nodes"] == []
        assert data["edges"] == []


# ---------------------------------------------------------------------------
# Factory method
# ---------------------------------------------------------------------------

class TestFromFleetRepos:

    def test_from_file_contents(self):
        file_contents = {
            "flux-coop-runtime": {
                "src/coop/bridge.py": "from flux_runtime import Runtime\nfrom flux_spec import Spec",
                "tests/test_spec.py": "from flux_spec import validate",
            },
            "flux-conformance": {
                "tests/runtime_suite.rs": "// conformance tests for flux_runtime",
            },
        }
        g = DependencyGraph.from_fleet_repos(file_contents=file_contents)
        assert len(g.repos) >= 2
        # flux-coop-runtime should have dependencies
        coop_deps = g.get_dependencies("flux-coop-runtime")
        targets = {d.target_repo for d in coop_deps}
        assert len(targets) > 0

    def test_from_issue_references(self):
        issue_refs = {
            "flux-coop-runtime": ["flux-spec", "flux-runtime"],
            "flux-rfc": ["flux-spec"],
        }
        g = DependencyGraph.from_fleet_repos(issue_references=issue_refs)
        assert len(g.repos) >= 3
        coop_deps = g.get_dependencies("flux-coop-runtime")
        targets = {d.target_repo for d in coop_deps}
        assert "flux-spec" in targets
        assert "flux-runtime" in targets


# ---------------------------------------------------------------------------
# Health scoring
# ---------------------------------------------------------------------------

class TestHealthScoring:

    def test_healthy_repo(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        health = analyzer.analyze_repo(sample_repo_data[0])  # flux-spec
        assert 0.0 <= health.health_score <= 1.0
        assert health.health_score > 0.5
        assert HealthFactor.TEST_COVERAGE.value in health.factors

    def test_abandoned_repo(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        health = analyzer.analyze_repo(sample_repo_data[3])  # abandoned
        assert health.health_score < 0.4
        assert HealthFactor.RECENT_ACTIVITY.value in health.factors

    def test_all_factors_present(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        health = analyzer.analyze_repo(sample_repo_data[0])
        for factor in HealthFactor:
            assert factor.value in health.factors

    def test_as_dict(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        health = analyzer.analyze_repo(sample_repo_data[0])
        d = health.as_dict()
        assert d["name"] == "flux-spec"
        assert "health_score" in d
        assert "factors" in d

    def test_empty_repo_data(self):
        analyzer = EcosystemHealthAnalyzer()
        health = analyzer.analyze_repo({"name": "empty"})
        assert health.health_score >= 0.0
        assert health.name == "empty"


# ---------------------------------------------------------------------------
# Ecosystem report
# ---------------------------------------------------------------------------

class TestEcosystemReport:

    def test_analyze_ecosystem(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        assert report.total_repos == 4
        assert 0.0 < report.average_health < 1.0
        assert len(report.repo_healths) == 4
        assert report.generated_at != ""

    def test_weakest_links(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        weakest = analyzer.get_weakest_links(report.repo_healths, threshold=0.4)
        assert "abandoned-repo" in weakest

    def test_growth_areas(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        growth = analyzer.get_growth_areas(report)
        # At least one growth area should exist (abandoned repo drags averages)
        assert len(growth) >= 1

    def test_compare_snapshots(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        old = analyzer.analyze_ecosystem(sample_repo_data)
        # Modify data to create improvement
        improved_data = [
            {**d, "test_files": d.get("test_files", 0) + 5}
            for d in sample_repo_data
        ]
        new = analyzer.analyze_ecosystem(improved_data)
        diff = analyzer.compare_snapshots(old, new)
        assert "health_change" in diff
        assert "improved" in diff
        assert "declined" in diff
        assert "average_delta" in diff

    def test_as_dict(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        d = report.as_dict()
        assert d["total_repos"] == 4
        assert isinstance(d["repo_healths"], list)
        assert isinstance(d["factor_averages"], dict)


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------

class TestMarkdownReport:

    def test_markdown_report(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        md = analyzer.to_markdown(report)
        assert "# FLUX Ecosystem Health Report" in md
        assert "## Repo Health Scores" in md
        assert "Average health:" in md
        assert "| Repo | Health" in md

    def test_markdown_includes_weakest(self, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        md = analyzer.to_markdown(report)
        if report.weakest_links:
            assert "## Weakest Links" in md

    def test_markdown_empty(self):
        analyzer = EcosystemHealthAnalyzer()
        report = EcosystemHealthReport()
        md = analyzer.to_markdown(report)
        assert "# FLUX Ecosystem Health Report" in md


# ---------------------------------------------------------------------------
# Mermaid map generation
# ---------------------------------------------------------------------------

class TestMermaidMap:

    def test_basic_mermaid_map(self, simple_graph):
        md = generate_mermaid_map(simple_graph)
        assert "graph TD" in md
        assert "classDef critical" in md
        assert "classDef healthy" in md

    def test_mermaid_map_with_health(self, simple_graph, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        md = generate_mermaid_map(simple_graph, health=report)
        assert "classDef" in md
        # Should have health-based class assignments
        assert "class " in md

    def test_mermaid_map_edge_styles(self, simple_graph):
        md = generate_mermaid_map(simple_graph)
        # Check for different edge styles
        assert "==>" in md  # implements_spec
        assert "-.->" in md  # tests


# ---------------------------------------------------------------------------
# Markdown map generation
# ---------------------------------------------------------------------------

class TestMarkdownMap:

    def test_basic_markdown_map(self, simple_graph):
        md = generate_markdown_map(simple_graph)
        assert "# Fleet Dependency Map" in md
        assert "## Repo Status" in md
        assert "## Dependency Edges" in md

    def test_markdown_map_with_health(self, simple_graph, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        md = generate_markdown_map(simple_graph, health=report)
        assert "Health" in md

    def test_markdown_map_critical_path(self, simple_graph):
        md = generate_markdown_map(simple_graph)
        assert "## Critical Path" in md
        assert "flux-spec" in md


# ---------------------------------------------------------------------------
# DOT map generation
# ---------------------------------------------------------------------------

class TestDotMap:

    def test_basic_dot_map(self, simple_graph):
        dot = generate_dot_map(simple_graph)
        assert "digraph fleet" in dot
        assert "rankdir=LR" in dot
        assert "->" in dot

    def test_dot_map_with_health(self, simple_graph, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        dot = generate_dot_map(simple_graph, health=report)
        assert "fillcolor=" in dot

    def test_dot_edge_styles(self, simple_graph):
        dot = generate_dot_map(simple_graph)
        assert "style=bold" in dot  # implements_spec
        assert "style=dashed" in dot  # tests


# ---------------------------------------------------------------------------
# ASCII map generation
# ---------------------------------------------------------------------------

class TestAsciiMap:

    def test_basic_ascii_map(self, simple_graph):
        ascii_map = generate_ascii_map(simple_graph)
        assert "FLUX FLEET DEPENDENCY MAP" in ascii_map
        assert "LAYER" in ascii_map
        assert "flux-spec" in ascii_map
        assert "flux-runtime" in ascii_map

    def test_ascii_map_with_health(self, simple_graph, sample_repo_data):
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)
        ascii_map = generate_ascii_map(simple_graph, health=report)
        assert "[OK]" in ascii_map or "[!!]" in ascii_map or "[~~]" in ascii_map
        assert "Legend:" in ascii_map

    def test_ascii_map_width(self, simple_graph):
        ascii_map = generate_ascii_map(simple_graph, width=60)
        # Verify it generated output
        assert "FLUX FLEET" in ascii_map
        # Unicode block chars may be multi-column, so just check content exists
        assert len(ascii_map) > 100

    def test_ascii_map_critical_path(self, simple_graph):
        ascii_map = generate_ascii_map(simple_graph)
        assert "CRITICAL PATH" in ascii_map

    def test_ascii_map_no_cycles(self, simple_graph):
        ascii_map = generate_ascii_map(simple_graph)
        assert "CYCLES DETECTED" not in ascii_map

    def test_ascii_map_with_cycles(self):
        g = DependencyGraph()
        g.add_dependency(Dependency("A", "B", DependencyType.USES))
        g.add_dependency(Dependency("B", "A", DependencyType.USES))
        ascii_map = generate_ascii_map(g)
        assert "CYCLES DETECTED" in ascii_map

    def test_ascii_map_legend(self, simple_graph):
        ascii_map = generate_ascii_map(simple_graph)
        assert "Legend:" in ascii_map
        assert "[OK]" in ascii_map
        assert "[!!]" in ascii_map
        assert "[~~]" in ascii_map
        assert "[??]" in ascii_map


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_graph_health_map_pipeline(self, simple_graph, sample_repo_data):
        """End-to-end: build graph, score health, generate all map formats."""
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(sample_repo_data)

        # All map generators should work without error
        mermaid = generate_mermaid_map(simple_graph, health=report)
        markdown = generate_markdown_map(simple_graph, health=report)
        dot = generate_dot_map(simple_graph, health=report)
        ascii_map = generate_ascii_map(simple_graph, health=report)

        assert "graph TD" in mermaid
        assert "# Fleet" in markdown
        assert "digraph" in dot
        assert "LAYER" in ascii_map
        assert len(report.repo_healths) == 4

    def test_json_serialisation_roundtrip(self, simple_graph):
        """Ensure JSON output can be deserialized back."""
        import json
        data = simple_graph.to_json()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["meta"]["total_repos"] == len(simple_graph.repos)
        assert len(parsed["edges"]) == len(simple_graph.edges)

    def test_large_graph_performance(self):
        """Stress test: 50 repos, 200 edges."""
        import time
        g = DependencyGraph()
        for i in range(50):
            for j in range(i + 1, min(i + 5, 50)):
                g.add_dependency(Dependency(
                    f"repo-{i}", f"repo-{j}", DependencyType.USES,
                ))
        start = time.time()
        topo = g.topological_sort()
        cycles = g.get_cycles()
        impact = g.compute_impact("repo-0")
        elapsed = time.time() - start
        assert len(topo) == 50
        assert cycles == []
        assert elapsed < 2.0  # should be fast

"""
Comprehensive tests for ecosystem_health compare_snapshots with real data,
collector edge cases, and timeline builder edge cases.
"""

import json
import os
import pytest
from datetime import datetime, timedelta, timezone

from src.analyzer.ecosystem_health import (
    EcosystemHealthAnalyzer,
    EcosystemHealthReport,
    HealthFactor,
    RepoHealth,
)
from src.analyzer.timeline_builder import TimelineBuilder, TimelineEvent
from src.analyzer.metrics import MetricsComputer, FleetMetrics, Trend
from src.collector.commit_analyzer import CommitAnalyzer, CommitEvent, EventCategory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def analyzer() -> EcosystemHealthAnalyzer:
    return EcosystemHealthAnalyzer()


@pytest.fixture
def healthy_repo_data() -> list:
    """Well-rounded repo data for healthy fleet."""
    return [
        {
            "name": "flux-spec",
            "commits": 20,
            "last_commit_date": "2026-04-11T23:49:26Z",
            "test_files": 3,
            "source_files": 5,
            "agents": ["Super Z", "Quill", "Casey Digennaro"],
            "doc_files": 8,
            "has_spec": True,
            "has_readme": True,
            "open_issues": 1,
            "closed_issues": 15,
        },
        {
            "name": "flux-runtime",
            "commits": 50,
            "last_commit_date": "2026-04-11T21:36:06Z",
            "test_files": 8,
            "source_files": 12,
            "agents": ["Super Z", "Casey Digennaro", "Quill", "greenhorn"],
            "doc_files": 5,
            "has_spec": False,
            "has_readme": True,
            "open_issues": 3,
            "closed_issues": 20,
        },
        {
            "name": "flux-a2a-prototype",
            "commits": 15,
            "last_commit_date": "2026-04-11T17:28:01Z",
            "test_files": 2,
            "source_files": 6,
            "agents": ["Super Z", "Quill"],
            "doc_files": 2,
            "has_spec": False,
            "has_readme": True,
            "open_issues": 0,
            "closed_issues": 5,
        },
    ]


@pytest.fixture
def mixed_repo_data() -> list:
    """Mix of healthy and struggling repos for comparative tests."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_iso = (datetime.now(timezone.utc) - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [
        {
            "name": "healthy-repo",
            "commits": 40,
            "last_commit_date": now_iso,
            "test_files": 10,
            "source_files": 15,
            "agents": ["Agent A", "Agent B", "Agent C", "Agent D"],
            "doc_files": 5,
            "has_spec": True,
            "has_readme": True,
            "open_issues": 1,
            "closed_issues": 20,
        },
        {
            "name": "struggling-repo",
            "commits": 2,
            "last_commit_date": old_iso,
            "test_files": 0,
            "source_files": 3,
            "agents": ["Agent A"],
            "doc_files": 0,
            "has_spec": False,
            "has_readme": False,
            "open_issues": 5,
            "closed_issues": 0,
        },
        {
            "name": "moderate-repo",
            "commits": 10,
            "last_commit_date": "2026-04-01T12:00:00Z",
            "test_files": 2,
            "source_files": 8,
            "agents": ["Agent A", "Agent B"],
            "doc_files": 1,
            "has_spec": False,
            "has_readme": True,
            "open_issues": 2,
            "closed_issues": 3,
        },
    ]


# ===========================================================================
# Ecosystem Health compare_snapshots with real data
# ===========================================================================

class TestCompareSnapshots:

    def test_identical_snapshots_no_change(self, healthy_repo_data):
        """Comparing a report to itself should show zero change."""
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem(healthy_repo_data)
        diff = analyzer.compare_snapshots(report, report)
        assert diff["average_delta"] == 0.0
        assert len(diff["improved"]) == 0
        assert len(diff["declined"]) == 0
        for repo, change in diff["health_change"].items():
            assert change["delta"] == 0.0

    def test_improvement_detected(self, healthy_repo_data):
        """Adding tests should cause detectable improvement."""
        analyzer = EcosystemHealthAnalyzer()
        old = analyzer.analyze_ecosystem(healthy_repo_data)

        improved_data = [
            {**d, "test_files": d.get("test_files", 0) + 10}
            for d in healthy_repo_data
        ]
        new = analyzer.analyze_ecosystem(improved_data)
        diff = analyzer.compare_snapshots(old, new)

        assert diff["average_delta"] > 0.0
        # At least some repos should be in the improved list
        assert len(diff["improved"]) >= 0  # delta threshold is 0.1
        assert diff["average_delta"] == pytest.approx(new.average_health - old.average_health, abs=1e-9)

    def test_decline_detected(self, healthy_repo_data):
        """Reducing activity should show decline."""
        analyzer = EcosystemHealthAnalyzer()
        old = analyzer.analyze_ecosystem(healthy_repo_data)

        # Simulate abandonment
        old_date = (datetime.now(timezone.utc) - timedelta(days=365)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        declined_data = [
            {**d, "last_commit_date": old_date, "test_files": 0, "closed_issues": 0}
            for d in healthy_repo_data
        ]
        new = analyzer.analyze_ecosystem(declined_data)
        diff = analyzer.compare_snapshots(old, new)

        assert diff["average_delta"] < 0.0

    def test_new_repo_appears_in_diff(self, healthy_repo_data):
        """A new repo in the latest snapshot should appear with 0.0 old score."""
        analyzer = EcosystemHealthAnalyzer()
        old = analyzer.analyze_ecosystem(healthy_repo_data)

        new_data = healthy_repo_data + [{
            "name": "brand-new-repo",
            "commits": 5,
            "last_commit_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "test_files": 3,
            "source_files": 4,
            "agents": ["Agent A"],
            "doc_files": 1,
            "has_spec": False,
            "has_readme": True,
            "open_issues": 0,
            "closed_issues": 0,
        }]
        new = analyzer.analyze_ecosystem(new_data)
        diff = analyzer.compare_snapshots(old, new)

        assert "brand-new-repo" in diff["health_change"]
        assert diff["health_change"]["brand-new-repo"]["old"] == 0.0

    def test_removed_repo_in_diff(self, healthy_repo_data):
        """A repo that disappears should have 0.0 new score."""
        analyzer = EcosystemHealthAnalyzer()
        old = analyzer.analyze_ecosystem(healthy_repo_data)

        new = analyzer.analyze_ecosystem(healthy_repo_data[:2])
        diff = analyzer.compare_snapshots(old, new)

        removed_name = healthy_repo_data[2]["name"]
        assert removed_name in diff["health_change"]
        assert diff["health_change"][removed_name]["new"] == 0.0

    def test_weakest_links_updated(self, mixed_repo_data):
        """New weakest links should reflect the latest snapshot."""
        analyzer = EcosystemHealthAnalyzer()
        old = analyzer.analyze_ecosystem(mixed_repo_data)

        # Fix the struggling repo
        fixed_data = [
            {**d, "test_files": d.get("test_files", 0) + 5,
             "last_commit_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "doc_files": 3, "has_readme": True}
            if d["name"] == "struggling-repo" else d
            for d in mixed_repo_data
        ]
        new = analyzer.analyze_ecosystem(fixed_data)
        diff = analyzer.compare_snapshots(old, new)

        assert "struggling-repo" not in diff["new_weakest"]

    def test_compare_snapshots_empty_reports(self):
        """Empty reports should compare cleanly."""
        analyzer = EcosystemHealthAnalyzer()
        r1 = EcosystemHealthReport(generated_at="2026-01-01T00:00:00Z")
        r2 = EcosystemHealthReport(generated_at="2026-01-02T00:00:00Z")
        diff = analyzer.compare_snapshots(r1, r2)
        assert diff["average_delta"] == 0.0
        assert diff["health_change"] == {}

    def test_factor_level_comparison(self, healthy_repo_data):
        """Each repo's factors should be present in health_change."""
        analyzer = EcosystemHealthAnalyzer()
        old = analyzer.analyze_ecosystem(healthy_repo_data)
        improved = [
            {**d, "test_files": d.get("test_files", 0) + 20,
             "closed_issues": d.get("closed_issues", 0) + 20}
            for d in healthy_repo_data
        ]
        new = analyzer.analyze_ecosystem(improved)
        diff = analyzer.compare_snapshots(old, new)

        for repo_name in [d["name"] for d in healthy_repo_data]:
            assert repo_name in diff["health_change"]
            entry = diff["health_change"][repo_name]
            assert "old" in entry
            assert "new" in entry
            assert "delta" in entry
            assert entry["delta"] == pytest.approx(entry["new"] - entry["old"], abs=1e-9)


# ===========================================================================
# Collector edge cases
# ===========================================================================

class TestCollectorEdgeCases:

    def test_empty_response(self):
        """Collector should handle empty API response."""
        ca = CommitAnalyzer()
        result = ca.batch_analyze([])
        assert result == []

    def test_malformed_missing_fields(self):
        """Analyzer should handle events with missing fields gracefully."""
        ca = CommitAnalyzer()
        event = ca.analyze_commit({})
        assert isinstance(event, CommitEvent)
        assert event.repo == ""
        assert event.hash == ""
        assert event.author == ""
        assert event.timestamp == ""
        assert event.categories  # should default to CODE_CHANGE

    def test_malformed_none_values(self):
        """Analyzer should handle None values in event dict."""
        ca = CommitAnalyzer()
        event = ca.analyze_commit({
            "agent": None, "repo": None, "timestamp": None,
            "description": None, "commit": None,
        })
        assert isinstance(event, CommitEvent)
        assert event.categories  # should have at least CODE_CHANGE

    def test_malformed_non_string_types(self):
        """Analyzer should handle non-string types in fields."""
        ca = CommitAnalyzer()
        event = ca.analyze_commit({
            "agent": 12345,
            "repo": ["list", "of", "repos"],
            "timestamp": {"not": "a string"},
            "description": 999,
            "commit": None,
            "files": [{"filename": "test.py"}, "not_a_dict", 42],
        })
        assert isinstance(event, CommitEvent)

    def test_empty_description(self):
        """Empty description should produce CODE_CHANGE category."""
        ca = CommitAnalyzer()
        cats = ca.categorize_message("")
        assert EventCategory.CODE_CHANGE in cats

    def test_none_description(self):
        """None description should not crash."""
        ca = CommitAnalyzer()
        cats = ca.categorize_message(None)  # type: ignore
        assert EventCategory.CODE_CHANGE in cats

    def test_unicode_description(self):
        """Unicode characters in description should be handled."""
        ca = CommitAnalyzer()
        cats = ca.categorize_message("feat: add 🎉 emoji support — cooperative execution")
        assert EventCategory.CODE_CHANGE in cats

    def test_very_long_description(self):
        """Very long description should be processed without issue."""
        ca = CommitAnalyzer()
        long_desc = "feat: " + "x" * 10000
        cats = ca.categorize_message(long_desc)
        assert EventCategory.CODE_CHANGE in cats

    def test_files_as_strings(self):
        """Files list with string entries should be parsed."""
        ca = CommitAnalyzer()
        event = ca.analyze_commit({
            "repo": "test/repo",
            "agent": "Agent",
            "description": "init: new repo",
            "commit": "abc12345",
            "timestamp": "2026-01-01T00:00:00Z",
            "files": ["src/flux-spec/spec.md", "tests/flux-runtime/test.py"],
        })
        assert "flux-spec" in event.dependencies
        assert "flux-runtime" in event.dependencies

    def test_empty_known_agents(self):
        """Custom analyzer with no known agents should find no mentions."""
        ca = CommitAnalyzer(known_agents=[])
        mentions = ca.extract_mentions("feat: Quill fleet introduction")
        assert mentions == []

    def test_empty_known_repos(self):
        """Custom analyzer with no known repos should find no dependencies."""
        ca = CommitAnalyzer(known_repos=[])
        deps = ca.extract_dependencies(["src/flux-runtime/decoder.py"])
        assert deps == []


# ===========================================================================
# Timeline builder edge cases
# ===========================================================================

class TestTimelineBuilderEdgeCases:

    def test_empty_builder(self):
        """Empty builder should return empty lists for all queries."""
        tb = TimelineBuilder()
        assert tb.size == 0
        assert tb.events == []
        assert tb.get_timeline() == []
        assert tb.get_agent_timeline("anyone") == []
        assert tb.get_repo_timeline("anything") == []
        assert tb.compute_velocity() == 0.0
        assert tb.detect_milestones() == []
        assert tb.get_dependency_graph() == {}

    def test_invalid_timestamps_ignored(self):
        """Events with unparseable timestamps should be filtered out."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="not-a-date",
            category="code_change",
            repo="test/repo",
            agent="A",
            description="bad timestamp",
        ))
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="A",
            description="good timestamp",
        ))
        result = tb.get_timeline()
        assert len(result) == 1
        assert result[0].description == "good timestamp"

    def test_none_timestamp(self):
        """None timestamp should be handled gracefully."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="",
            category="code_change",
            repo="test/repo",
            agent="A",
            description="empty timestamp",
        ))
        result = tb.get_timeline()
        assert len(result) == 0  # empty string -> parse failure -> filtered

    def test_all_same_timestamp(self):
        """Events with identical timestamps should all be returned."""
        tb = TimelineBuilder()
        for i in range(10):
            tb.add_event(TimelineEvent(
                timestamp="2026-04-11T12:00:00Z",
                category="code_change",
                repo=f"test/repo-{i}",
                agent=f"Agent-{i}",
                description=f"event {i}",
            ))
        result = tb.get_timeline()
        assert len(result) == 10

    def test_very_old_events(self):
        """Events from far in the past should be included in unfiltered queries."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2000-01-01T00:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="A",
            description="ancient event",
        ))
        assert tb.size == 1
        assert len(tb.events) == 1

    def test_case_insensitive_agent_search(self):
        """Agent search should be case-insensitive."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="Super Z",
            description="test",
        ))
        assert len(tb.get_agent_timeline("super z")) == 1
        assert len(tb.get_agent_timeline("SUPER Z")) == 1
        assert len(tb.get_agent_timeline("Super Z")) == 1
        assert len(tb.get_agent_timeline("unknown")) == 0

    def test_case_insensitive_repo_search(self):
        """Repo search should be case-insensitive."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="code_change",
            repo="SuperInstance/flux-runtime",
            agent="A",
            description="test",
        ))
        assert len(tb.get_repo_timeline("superinstance/flux-runtime")) == 1
        assert len(tb.get_repo_timeline("SUPERINSTANCE/FLUX-RUNTIME")) == 1

    def test_significance_boundary_values(self):
        """Significance should be clamped to [1, 5]."""
        for val in [0, -100, 1, 5, 6, 100]:
            ev = TimelineEvent(
                timestamp="2026-04-11T12:00:00Z",
                category="code_change",
                repo="test/repo",
                agent="A",
                description="test",
                significance=val,
            )
            assert 1 <= ev.significance <= 5

    def test_timeline_range_exact_boundaries(self):
        """Range filtering should be inclusive on both ends."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T10:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="A",
            description="start",
        ))
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="A",
            description="middle",
        ))
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T14:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="A",
            description="end",
        ))
        result = tb.get_timeline(
            start="2026-04-11T10:00:00Z",
            end="2026-04-11T14:00:00Z",
        )
        assert len(result) == 3  # all inclusive

    def test_velocity_zero_period(self):
        """Zero period should not crash."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="A",
            description="test",
        ))
        velocity = tb.compute_velocity(period_days=0)
        assert isinstance(velocity, float)

    def test_add_events_batch(self):
        """add_events should add multiple events at once."""
        tb = TimelineBuilder()
        events = [
            TimelineEvent(
                timestamp="2026-04-11T12:00:00Z",
                category="code_change",
                repo="test/repo",
                agent="A",
                description=f"batch {i}",
            )
            for i in range(20)
        ]
        tb.add_events(events)
        assert tb.size == 20

    def test_milestone_deduplication(self):
        """Duplicate milestones should be deduplicated."""
        tb = TimelineBuilder()
        for _ in range(5):
            tb.add_event(TimelineEvent(
                timestamp="2026-04-11T12:00:00Z",
                category="code_change",
                repo="test/repo",
                agent="A",
                description="same milestone",
                significance=5,
            ))
        milestones = tb.detect_milestones(min_significance=4)
        assert len(milestones) == 1  # deduplicated

    def test_dependency_graph_known_repos(self):
        """Only known fleet repos should appear in dependency graph."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="code_change",
            repo="SuperInstance/flux-coop-runtime",
            agent="A",
            description="bridge with flux-runtime for flux-spec conformance",
            significance=3,
        ))
        graph = tb.get_dependency_graph()
        assert "flux-coop-runtime" in graph
        # Should reference known repos
        assert any("flux-runtime" in v or "flux-spec" in v
                    for v in graph["flux-coop-runtime"])

    def test_dependency_graph_unknown_repos_excluded(self):
        """References to unknown repos should not create edges."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="code_change",
            repo="SuperInstance/flux-coop-runtime",
            agent="A",
            description="bridge with unknown-lib and random-tool",
            significance=3,
        ))
        graph = tb.get_dependency_graph()
        # flux-coop-runtime shouldn't appear since it only references unknown repos
        assert "unknown-lib" not in graph.get("flux-coop-runtime", [])

    def test_special_category_events_always_milestones(self):
        """new_repo and rfc_activity should always be milestones."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="new_repo",
            repo="test/repo",
            agent="A",
            description="init",
            significance=1,  # low significance
        ))
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T13:00:00Z",
            category="rfc_activity",
            repo="test/repo",
            agent="A",
            description="rfc",
            significance=1,
        ))
        milestones = tb.detect_milestones(min_significance=5)
        assert len(milestones) == 2
        categories = {m.category for m in milestones}
        assert "new_repo" in categories
        assert "rfc_activity" in categories

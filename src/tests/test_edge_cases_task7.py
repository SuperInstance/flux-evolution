"""
Edge case tests for collector, empty data, timeline boundaries, and health comparison.
Task ID 7 additions — 25 new tests.
"""

import json
import os
import pytest
from datetime import datetime, timedelta, timezone

from src.collector.commit_analyzer import (
    CommitAnalyzer,
    CommitEvent,
    EventCategory,
)
from src.analyzer.timeline_builder import TimelineBuilder, TimelineEvent
from src.analyzer.metrics import MetricsComputer, FleetMetrics, Trend
from src.analyzer.ecosystem_health import (
    EcosystemHealthAnalyzer,
    EcosystemHealthReport,
    HealthFactor,
    RepoHealth,
)
from src.analyzer.dependency_graph import DependencyGraph, Dependency, DependencyType
from src.exporter.markdown_report import generate_fleet_report
from src.exporter.ecosystem_map import generate_mermaid_map, generate_ascii_map


# ===========================================================================
# 1. Collector edge cases — input robustness (5 tests)
# ===========================================================================

class TestCollectorInputRobustness:

    def test_empty_string_description(self):
        """Empty string description should yield CODE_CHANGE."""
        ca = CommitAnalyzer()
        cats = ca.categorize_message("")
        assert EventCategory.CODE_CHANGE in cats

    def test_whitespace_only_description(self):
        """Whitespace-only description should yield CODE_CHANGE."""
        ca = CommitAnalyzer()
        cats = ca.categorize_message("   \t\n  ")
        assert EventCategory.CODE_CHANGE in cats

    def test_analyze_commit_empty_dict(self):
        """Completely empty dict should not crash."""
        ca = CommitAnalyzer()
        event = ca.analyze_commit({})
        assert isinstance(event, CommitEvent)
        assert event.repo == ""
        assert event.categories

    def test_analyze_commit_all_none(self):
        """All fields None should produce a valid CommitEvent."""
        ca = CommitAnalyzer()
        event = ca.analyze_commit({
            "agent": None, "repo": None, "timestamp": None,
            "description": None, "commit": None, "files": None,
        })
        assert isinstance(event, CommitEvent)
        assert EventCategory.CODE_CHANGE in event.categories

    def test_batch_analyze_single_item(self):
        """Batch with single commit should return list of length 1."""
        ca = CommitAnalyzer()
        result = ca.batch_analyze([{"description": "init: test repo"}])
        assert len(result) == 1
        assert EventCategory.NEW_REPO in result[0].categories

    def test_extract_mentions_non_string_message(self):
        """Non-string message to extract_mentions should not crash."""
        ca = CommitAnalyzer()
        mentions = ca.extract_mentions(12345)  # type: ignore
        assert isinstance(mentions, list)

    def test_categorize_multiple_test_patterns(self):
        """Multiple test patterns should not duplicate TEST_ADD."""
        ca = CommitAnalyzer()
        cats = ca.categorize_message("test: add test suite tests")
        # TEST_ADD should appear exactly once
        assert cats.count(EventCategory.TEST_ADD) == 1


# ===========================================================================
# 2. Empty data handling (5 tests)
# ===========================================================================

class TestEmptyDataHandling:

    def test_metrics_compute_empty_list(self):
        """MetricsComputer.compute with empty list should return zeros."""
        mc = MetricsComputer()
        m = mc.compute([])
        assert m.total_commits == 0
        assert m.active_agents == 0
        assert m.total_repos == 0
        assert m.test_coverage_ratio == 0.0

    def test_agent_matrix_empty(self):
        """Agent contribution matrix with no events should be empty dict."""
        mc = MetricsComputer()
        matrix = mc.agent_contribution_matrix([])
        assert matrix == {}

    def test_ecosystem_health_empty(self):
        """Ecosystem analysis with no repos should produce valid report."""
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem([])
        assert report.total_repos == 0
        assert report.average_health == 0.0
        assert report.generated_at != ""

    def test_dependency_graph_empty(self):
        """Empty dependency graph should have zero repos and edges."""
        g = DependencyGraph()
        assert len(g.repos) == 0
        assert len(g.edges) == 0
        assert g.get_critical_path() == []
        assert g.topological_sort() == []
        assert g.get_cycles() == []

    def test_fleet_report_empty_timeline(self):
        """Generating fleet report with empty timeline should not crash."""
        mc = MetricsComputer()
        metrics = mc.compute([])
        report = generate_fleet_report(timeline=[], metrics=metrics)
        assert "FLUX Fleet Evolution Report" in report


# ===========================================================================
# 3. Timeline boundary tests (5 tests)
# ===========================================================================

class TestTimelineBoundaries:

    def test_range_with_no_matching_events(self):
        """Range far from any event should return empty list."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="code_change", repo="test/repo",
            agent="A", description="event",
        ))
        result = tb.get_timeline(start="2099-01-01T00:00:00Z",
                                 end="2099-12-31T23:59:59Z")
        assert result == []

    def test_range_end_before_start(self):
        """End before start should return empty list."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00Z",
            category="code_change", repo="test/repo",
            agent="A", description="event",
        ))
        result = tb.get_timeline(start="2026-04-12T00:00:00Z",
                                 end="2026-04-10T00:00:00Z")
        assert result == []

    def test_future_events_included_in_unfiltered(self):
        """Future-timestamped events should appear in unfiltered timeline."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2099-12-31T23:59:59Z",
            category="code_change", repo="test/repo",
            agent="A", description="future event",
        ))
        assert tb.size == 1
        assert len(tb.events) == 1

    def test_microsecond_precision_timestamp(self):
        """Timestamps with microsecond precision should parse correctly."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T12:00:00.123456Z",
            category="code_change", repo="test/repo",
            agent="A", description="precise",
        ))
        result = tb.get_timeline()
        assert len(result) == 1

    def test_only_start_filter(self):
        """Filtering with only start should return all events from start onward."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T10:00:00Z",
            category="code_change", repo="test/repo",
            agent="A", description="before",
        ))
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T15:00:00Z",
            category="code_change", repo="test/repo",
            agent="A", description="after",
        ))
        result = tb.get_timeline(start="2026-04-11T12:00:00Z")
        assert len(result) == 1
        assert result[0].description == "after"

    def test_only_end_filter(self):
        """Filtering with only end should return all events up to end."""
        tb = TimelineBuilder()
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T10:00:00Z",
            category="code_change", repo="test/repo",
            agent="A", description="before",
        ))
        tb.add_event(TimelineEvent(
            timestamp="2026-04-11T15:00:00Z",
            category="code_change", repo="test/repo",
            agent="A", description="after",
        ))
        result = tb.get_timeline(end="2026-04-11T12:00:00Z")
        assert len(result) == 1
        assert result[0].description == "before"


# ===========================================================================
# 4. Health comparison edge cases (5 tests)
# ===========================================================================

class TestHealthComparisonEdgeCases:

    def test_perfect_health_repo(self):
        """Repo with max scores across all factors should score near 1.0."""
        analyzer = EcosystemHealthAnalyzer()
        repo_data = {
            "name": "perfect-repo",
            "commits": 100,
            "last_commit_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "test_files": 20,
            "source_files": 10,
            "agents": ["A", "B", "C", "D"],
            "doc_files": 10,
            "has_spec": True,
            "has_readme": True,
            "open_issues": 0,
            "closed_issues": 50,
        }
        health = analyzer.analyze_repo(repo_data)
        assert health.health_score >= 0.8

    def test_zero_everything_repo(self):
        """Repo with no data should still produce valid health assessment."""
        analyzer = EcosystemHealthAnalyzer()
        repo_data = {
            "name": "zero-repo",
            "commits": 0,
            "last_commit_date": "",
            "test_files": 0,
            "source_files": 0,
            "agents": [],
            "doc_files": 0,
            "has_spec": False,
            "has_readme": False,
            "open_issues": 0,
            "closed_issues": 0,
        }
        health = analyzer.analyze_repo(repo_data)
        assert 0.0 <= health.health_score < 0.5

    def test_compare_repos_same_health(self):
        """Two repos with identical scores should have zero delta."""
        analyzer = EcosystemHealthAnalyzer()
        data = {"name": "r1", "commits": 10, "agents": ["A"]}
        r1 = analyzer.analyze_repo(data)
        r2 = analyzer.analyze_repo({"name": "r2", "commits": 10, "agents": ["A"]})
        assert r1.health_score == r2.health_score

    def test_growth_areas_threshold_boundary(self):
        """Factor average at exactly threshold should not appear in growth areas."""
        analyzer = EcosystemHealthAnalyzer()
        # Create repos where all factors are exactly 0.5 (the default threshold)
        data = [
            {
                "name": f"repo-{i}",
                "commits": 10,
                "last_commit_date": "2026-04-11T12:00:00Z",
                "test_files": 5,
                "source_files": 10,
                "agents": ["A"],
                "doc_files": 1,
                "has_readme": True,
            }
            for i in range(5)
        ]
        report = analyzer.analyze_ecosystem(data)
        growth = analyzer.get_growth_areas(report, threshold=0.5)
        # Exactly at threshold should not be included (< not <=)
        for area in growth:
            assert "50%" not in area  # if avg is exactly 50%, it shouldn't appear

    def test_health_report_serialization_roundtrip(self):
        """Health report as_dict should contain all expected keys."""
        analyzer = EcosystemHealthAnalyzer()
        report = analyzer.analyze_ecosystem([
            {"name": "test", "commits": 5, "agents": ["A"]},
        ])
        d = report.as_dict()
        assert "generated_at" in d
        assert "total_repos" in d
        assert "average_health" in d
        assert "repo_healths" in d
        assert "weakest_links" in d
        assert "growth_areas" in d
        assert "recommendations" in d
        assert "factor_averages" in d


# ===========================================================================
# 5. Events JSONL with new cooperation/convergence events (3 tests)
# ===========================================================================

class TestNewEventTypes:

    def test_cooperation_event_in_jsonl(self):
        """events.jsonl should contain cooperation events after update."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "events.jsonl"
        )
        path = os.path.normpath(path)
        events = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        coop_events = [e for e in events if e.get("event_type") == "cooperation"]
        assert len(coop_events) >= 3

    def test_convergence_event_in_jsonl(self):
        """events.jsonl should contain convergence events after update."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "events.jsonl"
        )
        path = os.path.normpath(path)
        events = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        conv_events = [e for e in events if e.get("event_type") == "convergence"]
        assert len(conv_events) >= 2

    def test_new_events_analyzable(self):
        """All new events (cooperation + convergence) should be analyzable."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "events.jsonl"
        )
        path = os.path.normpath(path)
        analyzer = CommitAnalyzer()
        events = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        # All events should produce valid CommitEvents
        commit_events = analyzer.batch_analyze(events)
        assert len(commit_events) == len(events)
        for ce in commit_events:
            assert isinstance(ce, CommitEvent)
            assert len(ce.categories) >= 1

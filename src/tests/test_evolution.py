"""
Tests for the flux-evolution tracker.

Covers commit analysis, timeline building, metrics computation,
trend analysis, milestone detection, and markdown report generation.
"""

import json
import os
import pytest

from src.collector.commit_analyzer import (
    CommitAnalyzer,
    CommitEvent,
    EventCategory,
)
from src.analyzer.timeline_builder import (
    TimelineBuilder,
    TimelineEvent,
)
from src.analyzer.metrics import (
    FleetMetrics,
    MetricsComputer,
    Trend,
)
from src.exporter.markdown_report import generate_fleet_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def analyzer() -> CommitAnalyzer:
    return CommitAnalyzer()


@pytest.fixture
def sample_commits() -> list:
    return [
        {
            "event_type": "code_change",
            "agent": "Super Z",
            "repo": "SuperInstance/flux-spec",
            "commit": "b0151cb7",
            "timestamp": "2026-04-11T19:29:30Z",
            "description": "docs: .fluxvocab format v1.0 specification",
            "impact": {"files_changed": 1, "additions": 200, "deletions": 0},
        },
        {
            "event_type": "code_change",
            "agent": "Casey Digennaro",
            "repo": "SuperInstance/flux-runtime",
            "commit": "10f59472",
            "timestamp": "2026-04-11T20:23:26Z",
            "description": "test(a2a): protocol primitives — 25 tests, JSON round-trip + registry",
            "impact": {"files_changed": 2, "additions": 300, "deletions": 10},
        },
        {
            "event_type": "code_change",
            "agent": "Super Z",
            "repo": "SuperInstance/flux-rfc",
            "commit": "1861e3b6",
            "timestamp": "2026-04-11T23:49:26Z",
            "description": "rfc(0001): ISA canonical declaration — CANONICAL by evidence",
            "impact": {"files_changed": 1, "additions": 50, "deletions": 0},
        },
        {
            "event_type": "code_change",
            "agent": "Super Z",
            "repo": "SuperInstance/flux-coop-runtime",
            "commit": "f9c6aeb4",
            "timestamp": "2026-04-11T23:24:51Z",
            "description": "init: flux-coop-runtime — cooperative execution middle layer",
            "impact": {"files_changed": 5, "additions": 400, "deletions": 0},
        },
        {
            "event_type": "code_change",
            "agent": "Quill (Architect)",
            "repo": "SuperInstance/superz-vessel",
            "commit": "9f30a593",
            "timestamp": "2026-04-11T23:49:58Z",
            "description": "docs(recon): expanded ecosystem reconnaissance",
            "impact": {"files_changed": 3, "additions": 150, "deletions": 20},
        },
        {
            "event_type": "code_change",
            "agent": "Super Z",
            "repo": "SuperInstance/flux-runtime",
            "commit": "6f483825",
            "timestamp": "2026-04-11T21:36:06Z",
            "description": "feat(bottle): Quill fleet introduction + task claims",
            "impact": {"files_changed": 2, "additions": 80, "deletions": 0},
        },
    ]


@pytest.fixture
def sample_timeline_events() -> list:
    return [
        TimelineEvent(
            timestamp="2026-04-11T19:00:00Z",
            category="spec_change",
            repo="SuperInstance/flux-spec",
            agent="Super Z",
            description="Signal Language Specification v1.0",
            significance=5,
        ),
        TimelineEvent(
            timestamp="2026-04-11T20:00:00Z",
            category="test_add",
            repo="SuperInstance/flux-runtime",
            agent="Casey Digennaro",
            description="Protocol primitives tests — 25 tests",
            significance=3,
        ),
        TimelineEvent(
            timestamp="2026-04-11T21:00:00Z",
            category="new_repo",
            repo="SuperInstance/flux-coop-runtime",
            agent="Super Z",
            description="init: flux-coop-runtime",
            significance=5,
        ),
        TimelineEvent(
            timestamp="2026-04-11T22:00:00Z",
            category="rfc_activity",
            repo="SuperInstance/flux-rfc",
            agent="Super Z",
            description="rfc(0001): ISA canonical declaration",
            significance=4,
        ),
        TimelineEvent(
            timestamp="2026-04-11T23:00:00Z",
            category="cross_agent",
            repo="SuperInstance/superz-vessel",
            agent="Quill (Architect)",
            description="Quill ecosystem reconnaissance",
            significance=4,
        ),
        TimelineEvent(
            timestamp="2026-04-11T23:30:00Z",
            category="code_change",
            repo="SuperInstance/flux-runtime",
            agent="Super Z",
            description="feat(bottle): Quill fleet introduction",
            significance=3,
        ),
    ]


# ---------------------------------------------------------------------------
# Commit categorization tests
# ---------------------------------------------------------------------------

class TestCommitCategorization:

    def test_rfc_message(self, analyzer):
        cats = analyzer.categorize_message("rfc(0001): ISA canonical declaration")
        assert EventCategory.RFC_ACTIVITY in cats

    def test_rfc_bracket(self, analyzer):
        cats = analyzer.categorize_message("[RFC] Proposed change to SIGNAL.md")
        assert EventCategory.RFC_ACTIVITY in cats

    def test_feat_message(self, analyzer):
        cats = analyzer.categorize_message("feat(routing): semantic routing table")
        assert EventCategory.CODE_CHANGE in cats

    def test_test_message(self, analyzer):
        cats = analyzer.categorize_message("test(a2a): protocol primitives — 25 tests")
        assert EventCategory.TEST_ADD in cats

    def test_spec_message(self, analyzer):
        cats = analyzer.categorize_message("docs: .fluxvocab specification v1.0")
        assert EventCategory.SPEC_CHANGE in cats

    def test_init_message(self, analyzer):
        cats = analyzer.categorize_message("init: flux-coop-runtime — cooperative execution")
        assert EventCategory.NEW_REPO in cats

    def test_default_code_change(self, analyzer):
        cats = analyzer.categorize_message("chore: update dependencies")
        assert EventCategory.CODE_CHANGE in cats

    def test_combined_categories(self, analyzer):
        cats = analyzer.categorize_message("[RFC] test: conformance suite for spec changes")
        assert EventCategory.RFC_ACTIVITY in cats
        assert EventCategory.TEST_ADD in cats

    def test_init_initial_commit(self, analyzer):
        cats = analyzer.categorize_message("Initial commit")
        assert EventCategory.NEW_REPO in cats

    def test_batch_analyze(self, analyzer, sample_commits):
        events = analyzer.batch_analyze(sample_commits)
        assert len(events) == len(sample_commits)
        assert all(isinstance(e, CommitEvent) for e in events)


# ---------------------------------------------------------------------------
# Mention extraction tests
# ---------------------------------------------------------------------------

class TestMentionExtraction:

    def test_mention_quill(self, analyzer):
        mentions = analyzer.extract_mentions("feat(bottle): Quill fleet introduction")
        assert "Quill" in mentions

    def test_mention_super_z(self, analyzer):
        mentions = analyzer.extract_mentions("session 10: Super Z deep research")
        assert "Super Z" in mentions

    def test_mention_casey(self, analyzer):
        mentions = analyzer.extract_mentions("reviewed by Casey Digennaro")
        assert "Casey Digennaro" in mentions

    def test_no_mention(self, analyzer):
        mentions = analyzer.extract_mentions("fix typo in README")
        assert len(mentions) == 0

    def test_dependency_extraction(self, analyzer):
        files = ["src/flux-runtime/decoder.py", "tests/flux-spec/conformance.rs"]
        deps = analyzer.extract_dependencies(files)
        assert "flux-runtime" in deps
        assert "flux-spec" in deps

    def test_empty_files(self, analyzer):
        deps = analyzer.extract_dependencies([])
        assert deps == []

    def test_analyze_commit_full(self, analyzer, sample_commits):
        event = analyzer.analyze_commit(sample_commits[0])
        assert event.repo == "SuperInstance/flux-spec"
        assert event.author == "Super Z"
        assert len(event.categories) >= 1


# ---------------------------------------------------------------------------
# Timeline building and filtering tests
# ---------------------------------------------------------------------------

class TestTimelineBuilding:

    def test_add_and_get_events(self, sample_timeline_events):
        builder = TimelineBuilder()
        for ev in sample_timeline_events:
            builder.add_event(ev)
        assert builder.size == 6

    def test_get_timeline_sorted(self, sample_timeline_events):
        builder = TimelineBuilder()
        builder.add_events(sample_timeline_events)
        timeline = builder.events
        for i in range(1, len(timeline)):
            assert timeline[i].timestamp >= timeline[i - 1].timestamp

    def test_get_timeline_with_range(self, sample_timeline_events):
        builder = TimelineBuilder()
        builder.add_events(sample_timeline_events)
        result = builder.get_timeline(
            start="2026-04-11T20:00:00Z",
            end="2026-04-11T22:00:00Z",
        )
        assert len(result) == 3  # 20:00, 21:00, 22:00

    def test_get_agent_timeline(self, sample_timeline_events):
        builder = TimelineBuilder()
        builder.add_events(sample_timeline_events)
        result = builder.get_agent_timeline("Super Z")
        assert len(result) == 4  # 19:00, 21:00, 22:00, 23:30
        assert all(ev.agent == "Super Z" for ev in result)

    def test_get_repo_timeline(self, sample_timeline_events):
        builder = TimelineBuilder()
        builder.add_events(sample_timeline_events)
        result = builder.get_repo_timeline("SuperInstance/flux-runtime")
        assert len(result) == 2
        assert all("flux-runtime" in ev.repo for ev in result)

    def test_significance_clamped(self):
        ev = TimelineEvent(
            timestamp="2026-04-11T00:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="Test",
            description="test",
            significance=10,
        )
        assert ev.significance == 5

        ev2 = TimelineEvent(
            timestamp="2026-04-11T00:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="Test",
            description="test",
            significance=-3,
        )
        assert ev2.significance == 1


# ---------------------------------------------------------------------------
# Velocity computation tests
# ---------------------------------------------------------------------------

class TestVelocityComputation:

    def test_velocity_with_events(self, sample_timeline_events):
        builder = TimelineBuilder()
        builder.add_events(sample_timeline_events)
        velocity = builder.compute_velocity(period_days=7)
        # All events are from 2026-04-11; unless today is 2026-04-11
        # velocity might be 0. Test just that it returns a float.
        assert isinstance(velocity, float)
        assert velocity >= 0.0

    def test_velocity_empty(self):
        builder = TimelineBuilder()
        assert builder.compute_velocity(period_days=7) == 0.0


# ---------------------------------------------------------------------------
# Milestone detection tests
# ---------------------------------------------------------------------------

class TestMilestoneDetection:

    def test_high_significance_milestones(self, sample_timeline_events):
        builder = TimelineBuilder()
        builder.add_events(sample_timeline_events)
        milestones = builder.detect_milestones(min_significance=4)
        assert len(milestones) >= 3  # spec_change(5), new_repo(5), rfc(4), cross_agent(4)
        categories = {ev.category for ev in milestones}
        assert "new_repo" in categories
        assert "rfc_activity" in categories

    def test_no_milestones_when_low(self, sample_timeline_events):
        # Replace all significances with low values
        builder = TimelineBuilder()
        for ev in sample_timeline_events:
            ev.significance = 1
            builder.add_event(ev)
        milestones = builder.detect_milestones(min_significance=4)
        # new_repo and rfc_activity should still appear regardless
        assert len(milestones) >= 2


# ---------------------------------------------------------------------------
# Metrics computation tests
# ---------------------------------------------------------------------------

class TestMetricsComputation:

    def test_compute_basic(self, sample_timeline_events):
        mc = MetricsComputer()
        metrics = mc.compute(sample_timeline_events)
        assert isinstance(metrics, FleetMetrics)
        assert metrics.total_commits == 6
        assert metrics.active_agents == 3  # Super Z, Casey Digennaro, Quill
        assert metrics.test_coverage_ratio > 0
        assert metrics.total_repos > 0

    def test_compute_empty(self):
        mc = MetricsComputer()
        metrics = mc.compute([])
        assert metrics.total_commits == 0
        assert metrics.active_agents == 0

    def test_agent_contribution_matrix(self, sample_timeline_events):
        mc = MetricsComputer()
        matrix = mc.agent_contribution_matrix(sample_timeline_events)
        assert "Super Z" in matrix
        assert "Casey Digennaro" in matrix
        assert "Quill (Architect)" in matrix
        assert matrix["Super Z"]["commits"] == 4
        assert matrix["Casey Digennaro"]["commits"] == 1
        assert matrix["Super Z"]["repos"] >= 2

    def test_repo_health_score(self, sample_timeline_events):
        mc = MetricsComputer()
        # Filter events for flux-runtime only
        rt_events = [
            ev for ev in sample_timeline_events
            if "flux-runtime" in ev.repo
        ]
        score = mc.repo_health_score(rt_events)
        assert 0.0 <= score <= 1.0
        # Has tests + multiple agents = should score well
        assert score > 0.3

    def test_repo_health_empty(self):
        mc = MetricsComputer()
        assert mc.repo_health_score([]) == 0.0

    def test_identify_bottlenecks_healthy(self):
        mc = MetricsComputer()
        healthy = FleetMetrics(
            total_repos=10,
            total_commits=50,
            active_agents=5,
            cross_agent_commits=10,
            test_coverage_ratio=0.4,
            spec_completeness=0.8,
        )
        bottlenecks = mc.identify_bottlenecks(healthy)
        # With healthy metrics, should have few bottlenecks
        assert len(bottlenecks) <= 1

    def test_identify_bottlenecks_unhealthy(self):
        mc = MetricsComputer()
        unhealthy = FleetMetrics(
            total_repos=10,
            total_commits=5,
            active_agents=1,
            cross_agent_commits=0,
            test_coverage_ratio=0.0,
            spec_completeness=0.1,
        )
        bottlenecks = mc.identify_bottlenecks(unhealthy)
        assert len(bottlenecks) >= 3


# ---------------------------------------------------------------------------
# Trend analysis tests
# ---------------------------------------------------------------------------

class TestTrendAnalysis:

    def test_trend_empty(self):
        mc = MetricsComputer()
        assert mc.trend_analysis([]) == Trend.STABLE

    def test_trend_improving(self):
        mc = MetricsComputer()
        events = []
        # Create events in two windows: old window has 1, recent has 5
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(5):
            ts = (now - timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            events.append(TimelineEvent(
                timestamp=ts, category="code_change",
                repo="test/repo", agent="A", description=f"recent {i}",
            ))
        for i in range(5, 8):
            ts = (now - timedelta(days=8 - (i - 5))).strftime("%Y-%m-%dT%H:%M:%SZ")
            events.append(TimelineEvent(
                timestamp=ts, category="code_change",
                repo="test/repo", agent="A", description=f"old {i}",
            ))
        assert mc.trend_analysis(events, window_days=4) == Trend.IMPROVING

    def test_trend_declining(self):
        mc = MetricsComputer()
        events = []
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # 9 events in older window (days 6–10 ago), 1 in recent window (today)
        for i in range(1, 10):
            ts = (now - timedelta(days=5 + i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            events.append(TimelineEvent(
                timestamp=ts, category="code_change",
                repo="test/repo", agent="A", description=f"old {i}",
            ))
        # Only 1 in recent
        events.append(TimelineEvent(
            timestamp=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            category="code_change", repo="test/repo", agent="A", description="recent",
        ))
        assert mc.trend_analysis(events, window_days=5) == Trend.DECLINING


# ---------------------------------------------------------------------------
# Markdown report tests
# ---------------------------------------------------------------------------

class TestMarkdownReport:

    def test_report_contains_sections(self, sample_timeline_events):
        mc = MetricsComputer()
        metrics = mc.compute(sample_timeline_events)
        matrix = mc.agent_contribution_matrix(sample_timeline_events)
        builder = TimelineBuilder()
        builder.add_events(sample_timeline_events)
        milestones = builder.detect_milestones(min_significance=4)
        deps = builder.get_dependency_graph()

        report = generate_fleet_report(
            timeline=sample_timeline_events,
            metrics=metrics,
            agent_matrix=matrix,
            milestones=milestones,
            dependency_graph=deps,
        )

        assert "# FLUX Fleet Evolution Report" in report
        assert "## Overview" in report
        assert "## Timeline Highlights" in report
        assert "## Agent Contributions" in report
        assert "## Repo Health" in report
        assert "## Recommendations" in report

    def test_report_overview_values(self, sample_timeline_events):
        mc = MetricsComputer()
        metrics = mc.compute(sample_timeline_events)
        report = generate_fleet_report(
            timeline=sample_timeline_events,
            metrics=metrics,
        )
        assert "6" in report  # total commits
        assert "3" in report  # active agents

    def test_report_bottlenecks(self, sample_timeline_events):
        mc = MetricsComputer()
        unhealthy = FleetMetrics(
            total_repos=10, total_commits=5, active_agents=1,
            cross_agent_commits=0, test_coverage_ratio=0.0, spec_completeness=0.1,
        )
        bottlenecks = mc.identify_bottlenecks(unhealthy)
        report = generate_fleet_report(
            timeline=sample_timeline_events,
            metrics=unhealthy,
            bottlenecks=bottlenecks,
        )
        assert "## Bottlenecks" in report
        assert len(bottlenecks) > 0

    def test_report_is_markdown(self, sample_timeline_events):
        mc = MetricsComputer()
        metrics = mc.compute(sample_timeline_events)
        report = generate_fleet_report(
            timeline=sample_timeline_events,
            metrics=metrics,
        )
        # Basic markdown sanity checks
        assert "```" not in report  # no code blocks unless deps
        assert "|" in report  # table syntax
        assert "---" in report  # footer divider


# ---------------------------------------------------------------------------
# Dependency graph tests
# ---------------------------------------------------------------------------

class TestDependencyGraph:

    def test_graph_from_mentions(self):
        builder = TimelineBuilder()
        builder.add_event(TimelineEvent(
            timestamp="2026-04-11T20:00:00Z",
            category="code_change",
            repo="SuperInstance/flux-coop-runtime",
            agent="Super Z",
            description="feat: bridge flux-runtime cooperative execution with flux-spec conformance",
            significance=4,
        ))
        graph = builder.get_dependency_graph()
        assert "flux-coop-runtime" in graph
        assert "flux-runtime" in graph["flux-coop-runtime"]
        assert "flux-spec" in graph["flux-coop-runtime"]

    def test_graph_empty(self):
        builder = TimelineBuilder()
        builder.add_event(TimelineEvent(
            timestamp="2026-04-11T20:00:00Z",
            category="code_change",
            repo="test/repo",
            agent="A",
            description="fix typo",
            significance=1,
        ))
        graph = builder.get_dependency_graph()
        assert len(graph) == 0


# ---------------------------------------------------------------------------
# Events JSONL integration test
# ---------------------------------------------------------------------------

class TestEventsJsonl:

    def test_seed_events_file_exists_and_parsable(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "events.jsonl"
        )
        path = os.path.normpath(path)
        assert os.path.exists(path), f"events.jsonl not found at {path}"
        events = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        assert len(events) >= 20, f"Expected >= 20 events, got {len(events)}"
        for ev in events:
            assert "event_type" in ev
            assert "repo" in ev
            assert "timestamp" in ev
            assert "description" in ev

    def test_seed_events_analyzable(self):
        """Verify all seed events can be analyzed by CommitAnalyzer."""
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
        commit_events = analyzer.batch_analyze(events)
        assert len(commit_events) == len(events)
        # At least some events should have categories
        categorized = sum(1 for ce in commit_events if ce.categories)
        assert categorized > 0

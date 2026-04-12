"""
Fleet health metrics — computes aggregate measurements from timeline events.

Provides trend analysis, contribution matrices, repo health scores,
and bottleneck identification for the FLUX ecosystem.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Trend(Enum):
    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"


@dataclass
class FleetMetrics:
    """Aggregate health metrics for the fleet."""

    total_repos: int = 0
    total_commits: int = 0
    active_agents: int = 0
    cross_agent_commits: int = 0
    test_coverage_ratio: float = 0.0       # 0.0 – 1.0
    spec_completeness: float = 0.0          # 0.0 – 1.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_repos": self.total_repos,
            "total_commits": self.total_commits,
            "active_agents": self.active_agents,
            "cross_agent_commits": self.cross_agent_commits,
            "test_coverage_ratio": round(self.test_coverage_ratio, 3),
            "spec_completeness": round(self.spec_completeness, 3),
        }


@dataclass
class AgentContribution:
    """Per-agent contribution breakdown."""

    repos: int = 0
    commits: int = 0
    categories: Dict[str, int] = field(default_factory=dict)


class MetricsComputer:
    """Computes fleet health metrics from events and repo metadata."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    def compute(self, events: list, repos: Optional[List[str]] = None) -> FleetMetrics:
        """Compute aggregate fleet metrics from timeline events.

        *events* is a list of TimelineEvent objects (or any object with
        ``category``, ``agent``, ``repo`` attributes).
        """
        if not events:
            return FleetMetrics()

        total_commits = len(events)
        agent_set: set = set()
        repo_set: set = set()
        cross_agent_count = 0
        test_events = 0
        spec_events = 0

        for ev in events:
            agent = getattr(ev, "agent", "")
            repo = getattr(ev, "repo", "")
            cat = getattr(ev, "category", "")

            if agent:
                agent_set.add(agent)
            if repo:
                repo_set.add(repo)
            if cat in ("test_add", "TEST_ADD"):
                test_events += 1
            if cat in ("spec_change", "SPEC_CHANGE"):
                spec_events += 1
            if cat in ("cross_agent", "CROSS_AGENT"):
                cross_agent_count += 1

        provided_repos = len(repos) if repos else len(repo_set)

        return FleetMetrics(
            total_repos=provided_repos,
            total_commits=total_commits,
            active_agents=len(agent_set),
            cross_agent_commits=cross_agent_count,
            test_coverage_ratio=test_events / total_commits if total_commits else 0.0,
            spec_completeness=min(1.0, spec_events / max(provided_repos, 1)),
        )

    # ------------------------------------------------------------------
    # Trend analysis
    # ------------------------------------------------------------------

    def trend_analysis(self, events: list, window_days: int = 7) -> Trend:
        """Compare event frequency in the latest window vs. the preceding window.

        Returns IMPROVING if recent activity is higher, DECLINING if lower,
        STABLE if within ±10%.
        """
        if not events:
            return Trend.STABLE

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        recent_start = now - timedelta(days=window_days)
        older_start = now - timedelta(days=window_days * 2)

        recent_count = 0
        older_count = 0

        for ev in events:
            ts = getattr(ev, "timestamp", "")
            dt = self._parse_ts(ts)
            if dt is None:
                continue
            dt = dt.replace(tzinfo=None)
            if dt >= recent_start:
                recent_count += 1
            elif dt >= older_start:
                older_count += 1

        if older_count == 0:
            return Trend.IMPROVING if recent_count > 0 else Trend.STABLE

        ratio = recent_count / older_count
        if ratio > 1.10:
            return Trend.IMPROVING
        elif ratio < 0.90:
            return Trend.DECLINING
        return Trend.STABLE

    # ------------------------------------------------------------------
    # Contribution matrix
    # ------------------------------------------------------------------

    def agent_contribution_matrix(
        self, events: list,
    ) -> Dict[str, Dict[str, Any]]:
        """Build a dict of agent -> {repos: count, commits: count, categories: {...}}."""
        matrix: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "repos": set(),
            "commits": 0,
            "categories": defaultdict(int),
        })

        for ev in events:
            agent = getattr(ev, "agent", "unknown")
            repo = getattr(ev, "repo", "")
            cat = getattr(ev, "category", "")

            entry = matrix[agent]
            if repo:
                entry["repos"].add(repo)
            entry["commits"] += 1
            entry["categories"][cat] += 1

        # Convert sets to counts for JSON-serializable output
        result: Dict[str, Dict[str, Any]] = {}
        for agent, data in matrix.items():
            result[agent] = {
                "repos": len(data["repos"]),
                "commits": data["commits"],
                "categories": dict(data["categories"]),
            }
        return result

    # ------------------------------------------------------------------
    # Repo health
    # ------------------------------------------------------------------

    def repo_health_score(self, repo_events: list) -> float:
        """Compute a health score for a single repo based on its events.

        Scoring factors:
        - Has commits (base 0.2)
        - Has tests (0.0 – 0.2)
        - Has spec activity (0.0 – 0.2)
        - Has multiple agents (0.0 – 0.2)
        - Recent activity (0.0 – 0.2)
        """
        if not repo_events:
            return 0.0

        score = 0.2  # base score for existing

        # Test factor
        test_events = sum(
            1 for ev in repo_events
            if getattr(ev, "category", "") in ("test_add", "TEST_ADD")
        )
        if test_events > 0:
            score += min(0.2, 0.1 * test_events)

        # Spec factor
        spec_events = sum(
            1 for ev in repo_events
            if getattr(ev, "category", "") in ("spec_change", "SPEC_CHANGE")
        )
        if spec_events > 0:
            score += min(0.2, 0.2)

        # Multi-agent factor
        agents = {getattr(ev, "agent", "") for ev in repo_events} - {""}
        if len(agents) >= 2:
            score += 0.2
        elif len(agents) == 1:
            score += 0.1

        # Recency factor — events within last 7 days
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = now - timedelta(days=7)
        recent = sum(
            1 for ev in repo_events
            if self._parse_ts(getattr(ev, "timestamp", "")) is not None
            and self._parse_ts(getattr(ev, "timestamp", "")).replace(tzinfo=None) >= cutoff
        )
        total = len(repo_events)
        if total > 0:
            recency_ratio = recent / total
            score += 0.2 * recency_ratio

        return round(min(1.0, max(0.0, score)), 3)

    # ------------------------------------------------------------------
    # Bottleneck identification
    # ------------------------------------------------------------------

    def identify_bottlenecks(self, metrics: FleetMetrics) -> List[str]:
        """Identify areas needing attention based on current metrics."""
        issues: List[str] = []

        if metrics.test_coverage_ratio < 0.15:
            issues.append(
                f"Low test coverage ({metrics.test_coverage_ratio:.0%}) — "
                "add conformance tests across repos"
            )

        if metrics.cross_agent_commits < 3:
            issues.append(
                f"Low cross-agent collaboration ({metrics.cross_agent_commits} events) — "
                "encourage inter-agent PR reviews"
            )

        if metrics.active_agents < 3:
            issues.append(
                f"Few active agents ({metrics.active_agents}) — "
                "onboard more fleet members"
            )

        if metrics.spec_completeness < 0.5:
            issues.append(
                f"Spec completeness low ({metrics.spec_completeness:.0%}) — "
                "prioritise canonical spec updates"
            )

        if metrics.total_repos > 0 and metrics.total_commits / metrics.total_repos < 2:
            issues.append(
                f"Low commit density ({metrics.total_commits / metrics.total_repos:.1f} commits/repo) — "
                "repos may be abandoned or under-developed"
            )

        return issues

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ts(ts: str) -> Optional[datetime]:
        if not ts:
            return None
        try:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)
        except (ValueError, AttributeError):
            return None

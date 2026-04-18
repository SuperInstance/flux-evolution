"""
Timeline builder — constructs filtered timelines from fleet evolution events.

Supports time-range filtering, agent/repo scoping, velocity computation,
milestone detection, and dependency graph extraction.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class TimelineEvent:
    """A single event on the fleet timeline."""

    timestamp: str                # ISO-8601
    category: str                 # EventCategory value
    repo: str
    agent: str
    description: str
    significance: int = 1         # 1 (low) – 5 (critical)

    def __post_init__(self) -> None:
        self.significance = max(1, min(5, self.significance))

    @property
    def _dt(self) -> Optional[datetime]:
        """Parse timestamp for comparison. Returns None on parse failure."""
        try:
            # Handle both 'Z' suffix and no timezone
            ts = self.timestamp
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)
        except (ValueError, AttributeError):
            return None


@dataclass
class DependencyEdge:
    """An edge in the inter-repo dependency graph."""

    source: str   # repo that references another
    target: str   # repo being referenced
    weight: int = 1


class TimelineBuilder:
    """Builds and queries timelines of fleet evolution events."""

    def __init__(self) -> None:
        self._events: List[TimelineEvent] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_event(self, event: TimelineEvent) -> None:
        """Append an event to the timeline."""
        self._events.append(event)

    def add_events(self, events: List[TimelineEvent]) -> None:
        """Append multiple events."""
        self._events.extend(events)

    @property
    def events(self) -> List[TimelineEvent]:
        """Return all events, sorted by timestamp."""
        return sorted(self._events, key=lambda e: e.timestamp)

    @property
    def size(self) -> int:
        return len(self._events)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def get_timeline(self, start: Optional[str] = None,
                     end: Optional[str] = None) -> List[TimelineEvent]:
        """Return events within [start, end] ISO-8601 timestamps (inclusive)."""
        start_dt = self._parse(start) if start else None
        end_dt = self._parse(end) if end else None
        result: List[TimelineEvent] = []
        for ev in self.events:
            ev_dt = ev._dt
            if ev_dt is None:
                continue
            if start_dt and ev_dt < start_dt:
                continue
            if end_dt and ev_dt > end_dt:
                continue
            result.append(ev)
        return result

    def get_agent_timeline(self, agent_name: str) -> List[TimelineEvent]:
        """Return events authored by *agent_name* (case-insensitive)."""
        name_lower = agent_name.lower()
        return [
            ev for ev in self.events
            if ev.agent.lower() == name_lower
        ]

    def get_repo_timeline(self, repo_name: str) -> List[TimelineEvent]:
        """Return events touching *repo_name* (case-insensitive)."""
        repo_lower = repo_name.lower()
        return [
            ev for ev in self.events
            if ev.repo.lower() == repo_lower
        ]

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def compute_velocity(self, period_days: int = 7) -> float:
        """Compute average events per day over the last *period_days* days."""
        if not self._events or period_days <= 0:
            return 0.0
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = now - timedelta(days=period_days)
        count = sum(
            1 for ev in self._events
            if ev._dt and ev._dt.replace(tzinfo=None) >= cutoff
        )
        return round(count / period_days, 2)

    # ------------------------------------------------------------------
    # Milestone detection
    # ------------------------------------------------------------------

    def detect_milestones(self, min_significance: int = 4) -> List[TimelineEvent]:
        """Return high-significance events that represent fleet milestones.

        Milestones include:
        - Cross-repo commits (significance >= 4)
        - New repo creation (category == new_repo)
        - RFC consensus events (rfc_activity with high significance)
        """
        milestones: List[TimelineEvent] = []
        seen_hashes: Set[str] = set()

        for ev in self.events:
            if ev.significance >= min_significance:
                key = f"{ev.repo}:{ev.timestamp}:{ev.description[:40]}"
                if key not in seen_hashes:
                    seen_hashes.add(key)
                    milestones.append(ev)

        # Also include all NEW_REPO and RFC_ACTIVITY events regardless of score
        for ev in self.events:
            if ev.category in ("new_repo", "rfc_activity") and ev not in milestones:
                milestones.append(ev)

        return sorted(milestones, key=lambda e: e.timestamp)

    # ------------------------------------------------------------------
    # Dependency graph
    # ------------------------------------------------------------------

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Return a mapping of source_repo -> [target_repos].

        Builds this from events whose description references other repos
        and from explicit dependency edges captured in the timeline.
        """
        graph: Dict[str, List[str]] = defaultdict(list)
        known_repo_prefixes = {
            "flux-spec", "flux-runtime", "flux-a2a-prototype", "flux-lsp",
            "superz-vessel", "greenhorn-runtime", "greenhorn-onboarding",
            "flux-coop-runtime", "flux-rfc", "flux-evolution",
            "flux-knowledge-federation", "flux-sandbox",
        }

        for ev in self.events:
            desc_lower = ev.description.lower()
            source_short = ev.repo.split("/")[-1].lower() if "/" in ev.repo else ev.repo.lower()
            for repo in known_repo_prefixes:
                if repo != source_short and repo in desc_lower:
                    if repo not in graph[source_short]:
                        graph[source_short].append(repo)

        return dict(graph)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(ts: Optional[str]) -> Optional[datetime]:
        if not ts:
            return None
        try:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)
        except (ValueError, AttributeError):
            return None

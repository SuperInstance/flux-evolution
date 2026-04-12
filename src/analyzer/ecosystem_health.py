"""
Ecosystem health scoring — per-repo and fleet-wide health assessment.

Provides a multi-factor health score (0-1) for each repo, aggregates
into an ecosystem-wide report, and can diff snapshots over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ------------------------------------------------------------------
# Enums & data classes
# ------------------------------------------------------------------

class HealthFactor(Enum):
    """Individual scoring dimensions for repo health."""
    TEST_COVERAGE = "test_coverage"
    SPEC_COMPLETENESS = "spec_completeness"
    RECENT_ACTIVITY = "recent_activity"
    CROSS_AGENT_CONTRIBUTIONS = "cross_agent_contributions"
    DOCUMENTATION_QUALITY = "documentation_quality"
    ISSUE_RESOLUTION_RATE = "issue_resolution_rate"


@dataclass
class RepoHealth:
    """Health assessment for a single repository."""
    name: str
    health_score: float = 0.0  # 0.0 – 1.0
    factors: Dict[str, float] = field(default_factory=dict)
    details: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "health_score": round(self.health_score, 3),
            "factors": {k: round(v, 3) for k, v in self.factors.items()},
            "details": self.details,
        }


@dataclass
class EcosystemHealthReport:
    """Aggregate health report for the entire fleet."""
    generated_at: str = ""
    total_repos: int = 0
    average_health: float = 0.0
    repo_healths: List[RepoHealth] = field(default_factory=list)
    weakest_links: List[str] = field(default_factory=list)
    growth_areas: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    factor_averages: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_repos": self.total_repos,
            "average_health": round(self.average_health, 3),
            "repo_healths": [rh.as_dict() for rh in self.repo_healths],
            "weakest_links": self.weakest_links,
            "growth_areas": self.growth_areas,
            "recommendations": self.recommendations,
            "factor_averages": {k: round(v, 3) for k, v in self.factor_averages.items()},
        }


# ------------------------------------------------------------------
# Factor weights (tuneable)
# ------------------------------------------------------------------

_DEFAULT_WEIGHTS: Dict[HealthFactor, float] = {
    HealthFactor.TEST_COVERAGE: 0.20,
    HealthFactor.SPEC_COMPLETENESS: 0.15,
    HealthFactor.RECENT_ACTIVITY: 0.20,
    HealthFactor.CROSS_AGENT_CONTRIBUTIONS: 0.15,
    HealthFactor.DOCUMENTATION_QUALITY: 0.15,
    HealthFactor.ISSUE_RESOLUTION_RATE: 0.15,
}


# ------------------------------------------------------------------
# Analyzer
# ------------------------------------------------------------------

class EcosystemHealthAnalyzer:
    """Multi-factor health scorer for fleet repos and the ecosystem."""

    def __init__(
        self,
        weights: Optional[Dict[HealthFactor, float]] = None,
    ) -> None:
        self.weights = weights or dict(_DEFAULT_WEIGHTS)
        # Normalise weights
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    # ------------------------------------------------------------------
    # Single repo analysis
    # ------------------------------------------------------------------

    def analyze_repo(
        self,
        repo_data: Dict[str, Any],
    ) -> RepoHealth:
        """Score a single repo based on its metadata.

        *repo_data* is a dict with optional keys:
        - ``name`` (str): repo name
        - ``commits`` (int): total commit count
        - ``last_commit_date`` (str): ISO-8601 timestamp
        - ``test_files`` (int): number of test files
        - ``source_files`` (int): number of source files
        - ``agents`` (list[str]): contributing agent names
        - ``doc_files`` (int): number of documentation files
        - ``open_issues`` (int): open issue count
        - ``closed_issues`` (int): closed issue count
        - ``has_spec`` (bool): whether a spec file exists
        - ``has_readme`` (bool): whether a README exists
        """
        name = repo_data.get("name", "unknown")
        factors: Dict[str, float] = {}
        details: Dict[str, str] = {}

        # --- TEST_COVERAGE ---
        test_files = repo_data.get("test_files", 0)
        source_files = repo_data.get("source_files", 1)
        test_ratio = min(1.0, test_files / max(source_files, 1))
        # Bonus: extra credit for having any tests at all
        test_score = min(1.0, test_ratio * 1.5)
        factors[HealthFactor.TEST_COVERAGE.value] = test_score
        details[HealthFactor.TEST_COVERAGE.value] = (
            f"{test_files} test / {source_files} source files"
        )

        # --- SPEC_COMPLETENESS ---
        has_spec = repo_data.get("has_spec", False)
        commits = repo_data.get("commits", 0)
        if has_spec:
            spec_score = min(1.0, 0.5 + commits * 0.02)
        else:
            spec_score = min(0.3, commits * 0.01)  # some credit for activity
        factors[HealthFactor.SPEC_COMPLETENESS.value] = spec_score
        details[HealthFactor.SPEC_COMPLETENESS.value] = (
            "spec present" if has_spec else "no spec found"
        )

        # --- RECENT_ACTIVITY ---
        last_commit = repo_data.get("last_commit_date", "")
        recency = self._compute_recency(last_commit)
        factors[HealthFactor.RECENT_ACTIVITY.value] = recency
        details[HealthFactor.RECENT_ACTIVITY.value] = (
            f"last commit: {last_commit or 'never'}"
        )

        # --- CROSS_AGENT_CONTRIBUTIONS ---
        agents = repo_data.get("agents", [])
        unique_agents = len(set(agents))
        if unique_agents >= 4:
            agent_score = 1.0
        elif unique_agents >= 3:
            agent_score = 0.8
        elif unique_agents >= 2:
            agent_score = 0.6
        elif unique_agents == 1:
            agent_score = 0.3
        else:
            agent_score = 0.0
        factors[HealthFactor.CROSS_AGENT_CONTRIBUTIONS.value] = agent_score
        details[HealthFactor.CROSS_AGENT_CONTRIBUTIONS.value] = (
            f"{unique_agents} unique agent(s)"
        )

        # --- DOCUMENTATION_QUALITY ---
        doc_files = repo_data.get("doc_files", 0)
        has_readme = repo_data.get("has_readme", False)
        if has_readme and doc_files >= 3:
            doc_score = 1.0
        elif has_readme and doc_files >= 1:
            doc_score = 0.7
        elif has_readme:
            doc_score = 0.5
        elif doc_files >= 1:
            doc_score = 0.3
        else:
            doc_score = 0.0
        factors[HealthFactor.DOCUMENTATION_QUALITY.value] = doc_score
        details[HealthFactor.DOCUMENTATION_QUALITY.value] = (
            f"{doc_files} doc file(s), readme={'yes' if has_readme else 'no'}"
        )

        # --- ISSUE_RESOLUTION_RATE ---
        open_issues = repo_data.get("open_issues", 0)
        closed_issues = repo_data.get("closed_issues", 0)
        total_issues = open_issues + closed_issues
        if total_issues > 0:
            issue_score = closed_issues / total_issues
        else:
            # No issues could mean healthy (nothing to fix) or unmonitored
            issue_score = 0.5
        factors[HealthFactor.ISSUE_RESOLUTION_RATE.value] = issue_score
        details[HealthFactor.ISSUE_RESOLUTION_RATE.value] = (
            f"{closed_issues} closed / {total_issues} total"
        )

        # Weighted aggregate
        health_score = 0.0
        for factor_enum, weight in self.weights.items():
            health_score += weight * factors.get(factor_enum.value, 0.0)

        return RepoHealth(
            name=name,
            health_score=round(min(1.0, max(0.0, health_score)), 3),
            factors=factors,
            details=details,
        )

    # ------------------------------------------------------------------
    # Ecosystem-level analysis
    # ------------------------------------------------------------------

    def analyze_ecosystem(
        self,
        all_repos: List[Dict[str, Any]],
    ) -> EcosystemHealthReport:
        """Score all repos and produce an aggregate report."""
        healths = [self.analyze_repo(r) for r in all_repos]

        if not healths:
            return EcosystemHealthReport(
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        avg_health = sum(h.health_score for h in healths) / len(healths)
        weakest = self.get_weakest_links(healths)
        growth = self._compute_growth_areas(healths)
        recs = self._generate_recommendations(healths, weakest, growth)

        # Factor averages
        factor_keys = set()
        for h in healths:
            factor_keys.update(h.factors.keys())
        factor_avgs: Dict[str, float] = {}
        for fk in factor_keys:
            vals = [h.factors[fk] for h in healths if fk in h.factors]
            factor_avgs[fk] = sum(vals) / len(vals) if vals else 0.0

        return EcosystemHealthReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            total_repos=len(healths),
            average_health=round(avg_health, 3),
            repo_healths=sorted(healths, key=lambda h: h.health_score),
            weakest_links=weakest,
            growth_areas=growth,
            recommendations=recs,
            factor_averages=factor_avgs,
        )

    # ------------------------------------------------------------------
    # Comparative analysis
    # ------------------------------------------------------------------

    def get_weakest_links(
        self,
        healths: Optional[List[RepoHealth]] = None,
        threshold: float = 0.4,
    ) -> List[str]:
        """Return repos with health scores below *threshold*."""
        if healths is None:
            return []
        return [h.name for h in healths if h.health_score < threshold]

    def get_growth_areas(
        self,
        report: EcosystemHealthReport,
        threshold: float = 0.5,
    ) -> List[str]:
        """Factor domains across the ecosystem that need more work."""
        areas: List[str] = []
        factor_labels = {
            HealthFactor.TEST_COVERAGE.value: "Test coverage",
            HealthFactor.SPEC_COMPLETENESS.value: "Spec completeness",
            HealthFactor.RECENT_ACTIVITY.value: "Recent activity",
            HealthFactor.CROSS_AGENT_CONTRIBUTIONS.value: "Cross-agent collaboration",
            HealthFactor.DOCUMENTATION_QUALITY.value: "Documentation quality",
            HealthFactor.ISSUE_RESOLUTION_RATE.value: "Issue resolution",
        }
        for factor_key, avg_val in report.factor_averages.items():
            if avg_val < threshold:
                label = factor_labels.get(factor_key, factor_key)
                areas.append(f"{label} (avg {avg_val:.0%})")
        return areas

    def compare_snapshots(
        self,
        old: EcosystemHealthReport,
        new: EcosystemHealthReport,
    ) -> Dict[str, Any]:
        """Diff two ecosystem health snapshots.

        Returns a dict with:
        - ``health_change``: dict of repo -> (old_score, new_score, delta)
        - ``new_weakest``: repos that became weak
        - ``improved``: repos that improved significantly (>0.1)
        - ``declined``: repos that declined significantly (>0.1)
        - ``average_delta``: overall average change
        """
        old_map: Dict[str, float] = {h.name: h.health_score for h in old.repo_healths}
        new_map: Dict[str, float] = {h.name: h.health_score for h in new.repo_healths}

        all_repos = sorted(set(list(old_map.keys()) + list(new_map.keys())))

        health_change: Dict[str, Tuple[float, float, float]] = {}
        improved: List[str] = []
        declined: List[str] = []

        for repo in all_repos:
            old_val = old_map.get(repo, 0.0)
            new_val = new_map.get(repo, 0.0)
            delta = new_val - old_val
            health_change[repo] = (old_val, new_val, delta)
            if delta > 0.1:
                improved.append(repo)
            elif delta < -0.1:
                declined.append(repo)

        new_weakest = self.get_weakest_links(new.repo_healths)
        avg_delta = new.average_health - old.average_health

        return {
            "health_change": {
                repo: {"old": round(o, 3), "new": round(n, 3), "delta": round(d, 3)}
                for repo, (o, n, d) in health_change.items()
            },
            "new_weakest": new_weakest,
            "improved": improved,
            "declined": declined,
            "average_delta": round(avg_delta, 3),
        }

    # ------------------------------------------------------------------
    # Markdown rendering
    # ------------------------------------------------------------------

    def to_markdown(self, report: EcosystemHealthReport) -> str:
        """Render an ecosystem health report as markdown."""
        lines: List[str] = []
        lines.append("# FLUX Ecosystem Health Report\n")
        lines.append(f"> Generated: {report.generated_at}\n")
        lines.append(
            f"**Average health:** {report.average_health:.0%} "
            f"({report.total_repos} repos)\n"
        )

        # Health bar for each repo
        lines.append("\n## Repo Health Scores\n")
        lines.append("| Repo | Health | Test | Spec | Activity | Agents | Docs | Issues |")
        lines.append("|------|--------|------|------|----------|--------|------|--------|")
        for rh in sorted(report.repo_healths, key=lambda r: r.health_score, reverse=True):
            filled = int(rh.health_score * 5)
            bar = "[" + "#" * filled + "-" * (5 - filled) + "]"
            f = rh.factors
            lines.append(
                f"| {rh.name} | {rh.health_score:.0%} {bar} "
                f"| {f.get('test_coverage', 0):.0%} "
                f"| {f.get('spec_completeness', 0):.0%} "
                f"| {f.get('recent_activity', 0):.0%} "
                f"| {f.get('cross_agent_contributions', 0):.0%} "
                f"| {f.get('documentation_quality', 0):.0%} "
                f"| {f.get('issue_resolution_rate', 0):.0%} |"
            )

        if report.weakest_links:
            lines.append("\n## Weakest Links\n")
            for name in report.weakest_links:
                lines.append(f"- **{name}**: below health threshold")

        if report.growth_areas:
            lines.append("\n## Growth Areas\n")
            for area in report.growth_areas:
                lines.append(f"- {area}")

        if report.recommendations:
            lines.append("\n## Recommendations\n")
            for rec in report.recommendations:
                lines.append(f"- {rec}")

        lines.append("\n---\n*Generated by flux-evolution ecosystem health analyzer.*")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_recency(last_commit_date: str) -> float:
        """Score from 0-1 based on how recently the repo was updated."""
        if not last_commit_date:
            return 0.0

        try:
            if last_commit_date.endswith("Z"):
                last_commit_date = last_commit_date[:-1] + "+00:00"
            dt = datetime.fromisoformat(last_commit_date)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            days_ago = (now - dt).days
        except (ValueError, AttributeError):
            return 0.0

        if days_ago <= 1:
            return 1.0
        elif days_ago <= 7:
            return 0.9
        elif days_ago <= 14:
            return 0.7
        elif days_ago <= 30:
            return 0.5
        elif days_ago <= 60:
            return 0.3
        elif days_ago <= 90:
            return 0.15
        else:
            return 0.0

    def _compute_growth_areas(
        self, healths: List[RepoHealth],
    ) -> List[str]:
        """Identify factor domains that need work across the ecosystem."""
        factor_keys: Dict[str, List[float]] = {}
        for h in healths:
            for fk, fv in h.factors.items():
                factor_keys.setdefault(fk, []).append(fv)

        factor_labels = {
            HealthFactor.TEST_COVERAGE.value: "Test coverage",
            HealthFactor.SPEC_COMPLETENESS.value: "Spec completeness",
            HealthFactor.RECENT_ACTIVITY.value: "Recent activity",
            HealthFactor.CROSS_AGENT_CONTRIBUTIONS.value: "Cross-agent collaboration",
            HealthFactor.DOCUMENTATION_QUALITY.value: "Documentation quality",
            HealthFactor.ISSUE_RESOLUTION_RATE.value: "Issue resolution",
        }

        areas: List[str] = []
        for fk, vals in factor_keys.items():
            avg = sum(vals) / len(vals) if vals else 0.0
            if avg < 0.5:
                label = factor_labels.get(fk, fk)
                areas.append(f"{label} (avg {avg:.0%})")
        return areas

    @staticmethod
    def _generate_recommendations(
        healths: List[RepoHealth],
        weakest: List[str],
        growth: List[str],
    ) -> List[str]:
        """Generate actionable recommendations."""
        recs: List[str] = []

        if weakest:
            recs.append(
                f"**{len(weakest)} repo(s) below health threshold**: "
                f"{', '.join(weakest[:3])}"
                + ("..." if len(weakest) > 3 else "")
                + ". Prioritise triage."
            )

        if "Test coverage" in " ".join(growth):
            recs.append(
                "**Increase test coverage**: Add conformance tests to "
                "repos with low test-to-source file ratios."
            )

        if "Documentation quality" in " ".join(growth):
            recs.append(
                "**Improve documentation**: Add README files and "
                "architectural docs to under-documented repos."
            )

        if "Cross-agent collaboration" in " ".join(growth):
            recs.append(
                "**Encourage cross-agent contributions**: Use "
                "message-in-a-bottle to invite reviews from other fleet agents."
            )

        if "Spec completeness" in " ".join(growth):
            recs.append(
                "**Complete specs**: Add or update spec files for "
                "repos that lack formal specifications."
            )

        if not recs:
            recs.append("Ecosystem is healthy. Continue monitoring for regression.")

        return recs

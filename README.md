# flux-evolution

> Timeline visualization and analysis of the FLUX ecosystem's cooperative evolution

The fleet's meta-design principle states that the system studies its own cooperation patterns. flux-evolution makes those patterns visible by tracking changes across specs, code, agent skills, and cooperation events on a unified timeline.

## What It Tracks

1. **Spec Evolution** — Changes to flux-spec files (ISA.md, SIGNAL.md, etc.)
2. **Code Evolution** — Implementation changes across all FLUX VMs
3. **Agent Skill Evolution** — Career progression, expertise growth, badge acquisition
4. **Cooperation Events** — Bottle casts, PR reviews, cross-agent responses, RFC proposals
5. **Convergence Metrics** — ISA alignment scores, test pass rates, spec stability

## Timeline Data Model

```python
@dataclass
class EvolutionEvent:
    timestamp: str       # ISO-8601
    event_type: str      # "spec_change" | "code_change" | "skill_change" | "cooperation" | "convergence"
    agent: str           # Agent name
    repo: str            # Repository
    commit: str          # Commit SHA
    description: str     # Human-readable description
    impact: dict         # Quantified impact metrics
    metadata: dict       # Event-specific metadata
```

## Architecture

```
src/
  collector/              # GitHub-based fleet event collector
    github_collector.py   #   — Fetches commits, PRs, repo stats from GitHub API
    commit_analyzer.py    #   — Categorizes commits, extracts mentions & dependencies
  analyzer/               # Pattern identification and trend analysis
    timeline_builder.py   #   — Builds filtered timelines, detects milestones
    metrics.py            #   — Fleet metrics, trend analysis, contribution matrices
    ecosystem_health.py   #   — Multi-factor health scoring (per-repo & fleet-wide)
    dependency_graph.py   #   — Inter-repo dependency graph with cycle detection
  exporter/               # Report generation
    markdown_report.py    #   — Comprehensive fleet evolution markdown reports
    ecosystem_map.py      #   — Mermaid, DOT, ASCII, and Markdown map visualizations
  visualizer/             # (placeholder for future interactive visualizations)
```

## Pipeline

The end-to-end pipeline (`src/run_pipeline.py`) is **fully implemented**:

1. **Ingest** seed events from `data/events.jsonl`
2. **Analyze** commits via `CommitAnalyzer` (categorization, mentions, dependencies)
3. **Build** timeline via `TimelineBuilder` (filtering, milestones, velocity)
4. **Compute** metrics via `MetricsComputer` (fleet health, trends, bottlenecks)
5. **Score** ecosystem health via `EcosystemHealthAnalyzer` (multi-factor per-repo scoring)
6. **Map** dependency graph via `DependencyGraph` (cycle detection, impact analysis)
7. **Export** reports in 6 formats: Markdown fleet report, ecosystem health report, Mermaid map, DOT graph, ASCII map, JSON summary

Run with: `python src/run_pipeline.py` from the repo root.

## Current Status

- **Data Collection Pipeline**: Implemented — `GitHubCollector` gathers events from all 12 SuperInstance repos via the GitHub API, with commit analysis and categorization.
- **Analysis Engine**: Fully functional — timeline building, milestone detection, velocity computation, multi-factor health scoring, dependency graph analysis, trend analysis, and bottleneck identification.
- **Report Generation**: Fully functional — fleet evolution reports (markdown), ecosystem health reports, and dependency map generation in 4 formats (Mermaid, DOT, ASCII, Markdown table).
- **Seed Data**: 52 events collected from fleet activity on 2026-04-11–12, covering code changes, cooperation events (bottle casts, PR reviews), convergence events, spec updates, RFC activity, and repo initialization.
- **Test Suite**: 173 tests covering collectors, analyzers, exporters, edge cases, and end-to-end pipelines — all passing.
- **Deprecation Cleanup**: All `datetime.utcnow()` calls replaced with `datetime.now(timezone.utc)`.

### Next Steps

- [ ] Add interactive timeline visualization (D3.js / Plotly)
- [ ] Set up automated scheduled data collection
- [ ] Integrate convergence test results as a first-class event type
- [ ] Expand cooperation event tracking (PR reviews, bottle casts, RFC votes)

---

*"If you can't see the evolution, you can't improve it."*

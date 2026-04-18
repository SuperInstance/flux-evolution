"""
Pipeline script to process seed events and generate reports.
Run from repo root: python src/run_pipeline.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collector.commit_analyzer import CommitAnalyzer, EventCategory
from analyzer.timeline_builder import TimelineBuilder, TimelineEvent
from analyzer.metrics import MetricsComputer
from analyzer.ecosystem_health import EcosystemHealthAnalyzer
from analyzer.dependency_graph import DependencyGraph, Dependency, DependencyType
from exporter.markdown_report import generate_fleet_report
from exporter.ecosystem_map import generate_mermaid_map, generate_ascii_map, generate_dot_map, generate_markdown_map

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


def load_events():
    """Load events from events.jsonl."""
    path = os.path.join(DATA_DIR, "events.jsonl")
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def load_snapshot():
    """Load fleet snapshot."""
    path = os.path.join(DATA_DIR, "fleet-snapshot.json")
    with open(path) as f:
        return json.load(f)


def category_for_event(event):
    """Map event_type to TimelineEvent category."""
    etype = event.get("event_type", "code_change")
    desc = event.get("description", "").lower()

    if etype == "spec_change":
        return "spec_change"
    elif etype == "cooperation":
        return "cooperation"
    elif etype == "convergence":
        return "convergence"
    elif etype == "skill_change":
        return "skill_change"

    # Heuristic for code_change events
    if "init:" in desc or "initial commit" in desc:
        return "new_repo"
    elif "[rfc" in desc or desc.startswith("rfc"):
        return "rfc_activity"
    elif "test(" in desc or "tests" in desc:
        return "test_add"
    elif "spec" in desc or "specification" in desc:
        return "spec_change"
    else:
        return "code_change"


def significance_for_event(event):
    """Assign significance based on impact."""
    impact = event.get("impact", {})
    additions = impact.get("additions", 0)
    files = impact.get("files_changed", 0)

    if additions >= 400 or files >= 7:
        return 5
    elif additions >= 200 or files >= 4:
        return 4
    elif additions >= 100 or files >= 2:
        return 3
    elif additions >= 30:
        return 2
    return 1


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)

    print("Loading seed events...")
    events = load_events()
    print(f"  Loaded {len(events)} events")

    snapshot = load_snapshot()
    print(f"  Fleet snapshot: {snapshot['repos_tracked']} repos tracked")

    # --- Analyze commits ---
    analyzer = CommitAnalyzer()
    commit_events = analyzer.batch_analyze(events)
    print(f"  Analyzed {len(commit_events)} commits")

    # --- Build timeline ---
    builder = TimelineBuilder()
    for event in events:
        te = TimelineEvent(
            timestamp=event.get("timestamp", ""),
            category=category_for_event(event),
            repo=event.get("repo", ""),
            agent=event.get("agent", ""),
            description=event.get("description", ""),
            significance=significance_for_event(event),
        )
        builder.add_event(te)

    print(f"  Timeline built: {builder.size} events")

    # --- Compute metrics ---
    mc = MetricsComputer()
    metrics = mc.compute(builder.events)
    matrix = mc.agent_contribution_matrix(builder.events)
    milestones = builder.detect_milestones(min_significance=4)
    bottlenecks = mc.identify_bottlenecks(metrics)
    dep_graph = builder.get_dependency_graph()

    print(f"  Metrics: {metrics.total_commits} commits, {metrics.active_agents} agents, "
          f"{metrics.total_repos} repos")
    print(f"  Milestones detected: {len(milestones)}")
    print(f"  Bottlenecks: {len(bottlenecks)}")

    # --- Generate Fleet Evolution Report ---
    report = generate_fleet_report(
        timeline=builder.events,
        metrics=metrics,
        agent_matrix=matrix,
        milestones=milestones,
        bottlenecks=bottlenecks,
        dependency_graph=dep_graph,
    )
    report_path = os.path.join(REPORTS_DIR, "fleet-evolution-report.md")
    with open(report_path, "w") as f:
        f.write(report)
    print(f"  Written: {report_path}")

    # --- Build dependency graph from commit data ---
    dg = DependencyGraph()
    for ce in commit_events:
        repo = ce.repo.split("/")[-1] if "/" in ce.repo else ce.repo
        for dep in ce.dependencies:
            dg.add_dependency(Dependency(
                source_repo=repo,
                target_repo=dep,
                dep_type=DependencyType.USES,
                description=f"{repo} uses {dep}",
                evidence=[f"commit:{ce.hash}"],
            ))

    # --- Ecosystem health analysis ---
    # Derive repo metadata from events
    repo_agents = {}
    repo_commits = {}
    repo_test_files = {}
    repo_files = {}
    repo_last_commit = {}
    repo_doc_files = {}
    repo_has_readme = {}

    for event in events:
        repo = event.get("repo", "unknown")
        agent = event.get("agent", "")
        ts = event.get("timestamp", "")
        desc = event.get("description", "").lower()

        repo_agents.setdefault(repo, set()).add(agent)
        repo_commits[repo] = repo_commits.get(repo, 0) + 1
        if ts and (repo not in repo_last_commit or ts > repo_last_commit[repo]):
            repo_last_commit[repo] = ts
        if "test" in desc or "conformance" in desc:
            repo_test_files[repo] = repo_test_files.get(repo, 0) + 1
        if "readme" in desc:
            repo_has_readme[repo] = True
        if "docs:" in desc or "specification" in desc:
            repo_doc_files[repo] = repo_doc_files.get(repo, 0) + 1

    # Use snapshot data for issue counts
    snapshot_stats = snapshot.get("repo_stats", {})

    repo_data_list = []
    for repo_name, agents in repo_agents.items():
        short_name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
        snap = snapshot_stats.get(repo_name, {})
        repo_data_list.append({
            "name": short_name,
            "commits": repo_commits.get(repo_name, 0),
            "last_commit_date": repo_last_commit.get(repo_name, ""),
            "test_files": repo_test_files.get(repo_name, 0),
            "source_files": max(1, repo_commits.get(repo_name, 1)),
            "agents": list(agents),
            "doc_files": repo_doc_files.get(repo_name, 0),
            "has_spec": "flux-spec" in repo_name or "spec" in short_name,
            "has_readme": repo_has_readme.get(repo_name, False),
            "open_issues": snap.get("open_issues", 0),
            "closed_issues": snap.get("open_issues", 0),  # approximate
        })

    health_analyzer = EcosystemHealthAnalyzer()
    health_report = health_analyzer.analyze_ecosystem(repo_data_list)

    # --- Generate Ecosystem Health Report ---
    health_md = health_analyzer.to_markdown(health_report)
    health_path = os.path.join(REPORTS_DIR, "ecosystem-health-report.md")
    with open(health_path, "w") as f:
        f.write(health_md)
    print(f"  Written: {health_path}")

    # --- Generate Mermaid Map ---
    mermaid = generate_mermaid_map(dg, health=health_report)
    mermaid_path = os.path.join(REPORTS_DIR, "dependency-map.mmd")
    with open(mermaid_path, "w") as f:
        f.write(mermaid)
    print(f"  Written: {mermaid_path}")

    # --- Generate ASCII Map ---
    ascii_map = generate_ascii_map(dg, health=health_report)
    ascii_path = os.path.join(REPORTS_DIR, "dependency-map.txt")
    with open(ascii_path, "w") as f:
        f.write(ascii_map)
    print(f"  Written: {ascii_path}")

    # --- Generate DOT Map ---
    dot = generate_dot_map(dg, health=health_report)
    dot_path = os.path.join(REPORTS_DIR, "dependency-map.dot")
    with open(dot_path, "w") as f:
        f.write(dot)
    print(f"  Written: {dot_path}")

    # --- Generate JSON summary ---
    summary = {
        "generated_at": health_report.generated_at,
        "total_events": len(events),
        "total_repos": metrics.total_repos,
        "total_commits": metrics.total_commits,
        "active_agents": metrics.active_agents,
        "milestones": len(milestones),
        "average_health": health_report.average_health,
        "weakest_links": health_report.weakest_links,
        "growth_areas": health_report.growth_areas,
        "agent_summary": matrix,
        "bottlenecks": bottlenecks,
    }
    summary_path = os.path.join(REPORTS_DIR, "pipeline-summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  Written: {summary_path}")

    print(f"\nPipeline complete! {len(os.listdir(REPORTS_DIR))} reports generated.")


if __name__ == "__main__":
    main()

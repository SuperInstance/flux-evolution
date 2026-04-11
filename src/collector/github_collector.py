"""
GitHub-based fleet event collector.

Gathers events from SuperInstance repos via GitHub API,
producing an append-only event log for the evolution tracker.
"""

import json
import time
from typing import List, Dict, Any, Optional


class GitHubCollector:
    """Collects fleet evolution events from GitHub API."""

    DEFAULT_REPOS = [
        "SuperInstance/flux-spec",
        "SuperInstance/flux-runtime",
        "SuperInstance/flux-a2a-prototype",
        "SuperInstance/flux-lsp",
        "SuperInstance/superz-vessel",
        "SuperInstance/greenhorn-runtime",
        "SuperInstance/greenhorn-onboarding",
        "SuperInstance/flux-coop-runtime",
        "SuperInstance/flux-rfc",
        "SuperInstance/flux-evolution",
        "SuperInstance/flux-knowledge-federation",
        "SuperInstance/flux-sandbox",
    ]

    def __init__(self, token: str):
        self.token = token

    def _api(self, url: str) -> Any:
        """Make GitHub API request."""
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def collect_commits(self, repo: str, per_page: int = 30) -> List[Dict]:
        """Collect recent commits from a repo."""
        url = f"https://api.github.com/repos/{repo}/commits?per_page={per_page}"
        data = self._api(url)
        events = []
        for commit in data:
            events.append({
                "event_type": "code_change",
                "agent": commit.get("commit", {}).get("author", {}).get("name", "unknown"),
                "repo": repo,
                "commit": commit.get("sha", "")[:8],
                "timestamp": commit.get("commit", {}).get("author", {}).get("date", ""),
                "description": commit.get("commit", {}).get("message", "").split("\n")[0],
                "impact": {
                    "files_changed": len(commit.get("files", [])),
                    "additions": sum(f.get("additions", 0) for f in commit.get("files", [])),
                    "deletions": sum(f.get("deletions", 0) for f in commit.get("files", [])),
                },
            })
        return events

    def collect_open_prs(self, repo: str) -> List[Dict]:
        """Collect open PRs (cooperation events)."""
        url = f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=20"
        data = self._api(url)
        events = []
        for pr in data:
            events.append({
                "event_type": "cooperation",
                "agent": pr.get("user", {}).get("login", "unknown"),
                "repo": repo,
                "commit": f"PR#{pr.get('number', '')}",
                "timestamp": pr.get("created_at", ""),
                "description": f"PR: {pr.get('title', '')}",
                "impact": {
                    "type": "pull_request",
                    "state": "open",
                    "comments": pr.get("comments", 0),
                    "review_comments": pr.get("review_comments", 0),
                },
            })
        return events

    def collect_repo_stats(self) -> Dict[str, Dict]:
        """Collect basic stats for all tracked repos."""
        stats = {}
        for repo in self.DEFAULT_REPOS:
            try:
                url = f"https://api.github.com/repos/{repo}"
                data = self._api(url)
                stats[repo] = {
                    "stars": data.get("stargazers_count", 0),
                    "forks": data.get("forks_count", 0),
                    "open_issues": data.get("open_issues_count", 0),
                    "size_kb": data.get("size", 0),
                    "language": data.get("language", "unknown"),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                }
            except Exception:
                stats[repo] = {"error": "failed to fetch"}
        return stats

    def collect_all_events(self) -> List[Dict]:
        """Collect events from all tracked repos."""
        all_events = []
        for repo in self.DEFAULT_REPOS:
            try:
                commits = self.collect_commits(repo, per_page=5)
                all_events.extend(commits)
            except Exception:
                pass
        return all_events

    def collect_fleet_snapshot(self) -> Dict[str, Any]:
        """Produce a point-in-time fleet snapshot."""
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "repos_tracked": len(self.DEFAULT_REPOS),
            "repo_stats": self.collect_repo_stats(),
            "total_events": len(self.collect_all_events()),
        }

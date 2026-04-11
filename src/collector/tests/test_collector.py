"""Tests for the GitHub collector."""
import pytest
from unittest.mock import patch
from src.collector.github_collector import GitHubCollector


@pytest.fixture
def collector():
    return GitHubCollector("fake-token")


class TestGitHubCollector:
    def test_default_repos(self, collector):
        assert len(collector.DEFAULT_REPOS) >= 10
        assert "SuperInstance/flux-spec" in collector.DEFAULT_REPOS
        assert "SuperInstance/flux-coop-runtime" in collector.DEFAULT_REPOS

    def test_collect_commits(self, collector):
        mock_response = [{
            "sha": "abc123456789",
            "commit": {"author": {"name": "Quill", "date": "2026-04-12T12:00:00Z"},
                       "message": "feat: add cooperative runtime"},
            "files": [{"additions": 100, "deletions": 10}],
        }]
        with patch.object(collector, '_api', return_value=mock_response):
            events = collector.collect_commits("SuperInstance/flux-coop-runtime")
        assert len(events) == 1
        assert events[0]["agent"] == "Quill"
        assert events[0]["event_type"] == "code_change"
        assert events[0]["impact"]["additions"] == 100

    def test_collect_open_prs(self, collector):
        mock_response = [{
            "number": 4, "title": "Fix conformance tests",
            "user": {"login": "SuperInstance"},
            "created_at": "2026-04-11T20:00:00Z",
            "comments": 3, "review_comments": 1,
        }]
        with patch.object(collector, '_api', return_value=mock_response):
            events = collector.collect_open_prs("SuperInstance/flux-runtime")
        assert len(events) == 1
        assert events[0]["event_type"] == "cooperation"

    def test_collect_fleet_snapshot(self, collector):
        mock_stats = {
            "stars": 0, "forks": 0, "open_issues": 2,
            "size": 100, "language": "Python", "created_at": "", "updated_at": "",
        }
        mock_commits = [{
            "sha": "x", "commit": {
                "author": {"name": "A", "date": ""}, "message": "x", "files": [],
            },
        }]
        with patch.object(collector, '_api', return_value=mock_stats):
            snapshot = collector.collect_fleet_snapshot()
        assert "timestamp" in snapshot
        assert "repo_stats" in snapshot

    def test_collect_all_events_multiple_repos(self, collector):
        single = [{
            "sha": "x", "commit": {
                "author": {"name": "A", "date": ""}, "message": "x", "files": [],
            },
        }]
        with patch.object(collector, '_api', return_value=single):
            events = collector.collect_all_events()
        assert len(events) >= len(collector.DEFAULT_REPOS)

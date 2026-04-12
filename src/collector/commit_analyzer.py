"""
Commit analyzer — extracts fleet evolution events from raw commit data.

Categorizes commits, extracts agent mentions, and identifies dependency
relationships between repos based on files changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional


class EventCategory(Enum):
    """Classification of commit impact on the fleet."""

    SPEC_CHANGE = "spec_change"
    CODE_CHANGE = "code_change"
    TEST_ADD = "test_add"
    RFC_ACTIVITY = "rfc_activity"
    CROSS_AGENT = "cross_agent"
    NEW_REPO = "new_repo"
    DEPENDENCY = "dependency"


@dataclass
class CommitEvent:
    """A single commit, enriched with categorization and metadata."""

    repo: str
    hash: str
    author: str
    timestamp: str
    message: str
    files_changed: List[str] = field(default_factory=list)
    categories: List[EventCategory] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


# Known fleet agents for mention extraction
KNOWN_AGENTS = [
    "quill", "super z", "oracle1", "oracle", "casey", "greenhorn",
    "mechanic", "navigator", "sentry", "librarian", "polln",
    "z user", "superinstance",
]

# Known fleet repos for dependency extraction
KNOWN_REPOS = [
    "flux-spec", "flux-runtime", "flux-a2a-prototype", "flux-lsp",
    "superz-vessel", "greenhorn-runtime", "greenhorn-onboarding",
    "flux-coop-runtime", "flux-rfc", "flux-evolution",
    "flux-knowledge-federation", "flux-sandbox",
]

# Patterns that indicate init / new repo
_INIT_PATTERNS = [
    r"^init\b",
    r"\binitial commit\b",
    r"\bfirst commit\b",
    r"^chore:\s*initial",
]


class CommitAnalyzer:
    """Analyzes raw commit data to produce categorized CommitEvents."""

    def __init__(self, known_agents: Optional[List[str]] = None,
                 known_repos: Optional[List[str]] = None):
        self.known_agents = set(
            (a or "agent").lower() for a in (known_agents or KNOWN_AGENTS)
        )
        self.known_repos = set(
            (r or "repo").lower() for r in (known_repos or KNOWN_REPOS)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_commit(self, commit_data: Dict[str, Any]) -> CommitEvent:
        """Analyze a single commit dict (GitHub-collector format) into a CommitEvent."""
        message = commit_data.get("description", "")
        raw_files = commit_data.get("files", [])
        # Files may come as list of strings or list of dicts with "filename" key
        files_changed: List[str] = []
        for f in raw_files:
            if isinstance(f, str):
                files_changed.append(f)
            elif isinstance(f, dict):
                files_changed.append(f.get("filename", ""))

        categories = self.categorize_message(message)
        mentions = self.extract_mentions(message)
        dependencies = self.extract_dependencies(files_changed)

        # Additional category: if agent name is not the author, it's cross-agent
        author_lower = commit_data.get("agent", "").lower()
        for mention in mentions:
            if mention.lower() not in author_lower:
                if EventCategory.CROSS_AGENT not in categories:
                    categories.append(EventCategory.CROSS_AGENT)
                break

        return CommitEvent(
            repo=commit_data.get("repo", ""),
            hash=commit_data.get("commit", ""),
            author=commit_data.get("agent", ""),
            timestamp=commit_data.get("timestamp", ""),
            message=message,
            files_changed=files_changed,
            categories=categories,
            mentions=mentions,
            dependencies=dependencies,
        )

    def categorize_message(self, message: str) -> List[EventCategory]:
        """Heuristic categorization based on commit message content."""
        cats: List[EventCategory] = []
        msg_lower = message.lower()

        # RFC activity
        if re.search(r"\[rfc", msg_lower) or re.search(r"^rfc[\(:]", msg_lower):
            cats.append(EventCategory.RFC_ACTIVITY)

        # Spec change (docs in flux-spec or explicit spec keyword)
        if re.search(r"\bspec[\-_]", msg_lower) or re.search(r"specification", msg_lower):
            cats.append(EventCategory.SPEC_CHANGE)

        # Test addition
        if re.search(r"^test[\(:]", msg_lower) or re.search(r"\btests?\b", msg_lower):
            if EventCategory.TEST_ADD not in cats:
                cats.append(EventCategory.TEST_ADD)

        # New repo
        for pat in _INIT_PATTERNS:
            if re.search(pat, msg_lower):
                if EventCategory.NEW_REPO not in cats:
                    cats.append(EventCategory.NEW_REPO)
                break

        # Default to CODE_CHANGE if nothing else matched
        if not cats:
            cats.append(EventCategory.CODE_CHANGE)

        return cats

    def extract_mentions(self, message: str) -> List[str]:
        """Extract agent names mentioned in a commit message."""
        msg_lower = message.lower()
        found: List[str] = []
        for agent in sorted(self.known_agents, key=len, reverse=True):
            if agent in msg_lower:
                # Normalise to display form
                found.append(self._display_name(agent))
        return found

    def extract_dependencies(self, files_changed: List[str]) -> List[str]:
        """Identify repos referenced by the files touched in a commit."""
        deps: List[str] = []
        for repo in self.known_repos:
            for f in files_changed:
                if repo.lower() in f.lower():
                    deps.append(repo)
                    break
        return deps

    def batch_analyze(self, commits: List[Dict[str, Any]]) -> List[CommitEvent]:
        """Analyze a batch of commits."""
        return [self.analyze_commit(c) for c in commits]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _display_name(lower_name: str) -> str:
        """Convert a lower-case agent name to display form."""
        mapping = {
            "super z": "Super Z",
            "oracle1": "Oracle1",
            "oracle": "Oracle1",
            "casey": "Casey Digennaro",
            "z user": "Z User",
            "superinstance": "superinstance",
        }
        return mapping.get(lower_name, lower_name.title())

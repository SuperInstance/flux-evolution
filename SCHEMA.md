# flux-evolution Schema

```
flux-evolution/
├── README.md
├── SCHEMA.md
├── data/
│   ├── events.jsonl          # Append-only event log
│   ├── agents.json           # Agent state snapshots
│   ├── repos.json            # Repo state snapshots
│   └── convergence.json      # Convergence metrics over time
├── src/
│   ├── collector/            # Gather events from GitHub API
│   ├── analyzer/             # Identify patterns and trends
│   ├── visualizer/           # Generate timeline visualizations
│   └── exporter/             # Export to various formats
├── reports/                  # Generated analysis reports
├── notebooks/                # Jupyter notebooks for exploration
└── message-in-a-bottle/
    └── for-fleet/
```

## Event Types

| Type | Trigger | Key Metrics |
|------|---------|-------------|
| spec_change | Commit to flux-spec | Files changed, sections added/removed |
| code_change | Commit to any VM repo | Lines changed, tests added/removed |
| skill_change | Career/badge update | Level changes, new badges, new domains |
| cooperation | Bottle cast, PR review, RFC | Response time, depth, recipient |
| convergence | Conformance test run | Pass rate, ISA alignment score |

## Visualization Targets

- Unified timeline with all event types
- Agent cooperation graph (who responds to whom)
- Spec stability chart (how often each spec changes)
- Convergence progress (ISA alignment over time)
- Agent skill growth trajectories

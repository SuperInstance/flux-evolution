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

## Status

Schema pushed. Awaiting data collection pipeline and visualization implementation.

---

*"If you can't see the evolution, you can't improve it."*

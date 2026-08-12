# Production-Grade Agentic AI Systems

**OpenAgentOS** — an open-source enterprise runtime for autonomous agents, plus real
enterprise applications built on it.

Not chatbots. Not RAG demos. Agents that operate businesses: durable execution,
checkpoint recovery, idempotent side effects, human approval, agent memory,
observability, evaluation, audit, and replay.

## The runtime

```
User → Planner → Workflow Graph → Checkpoint → Memory → Tool Router
     → Execution → Verification → Human Approval → Audit → Replay
```

Eight modules, specified in [ENTERPRISE.md](ENTERPRISE.md):

| # | Module | Core tech |
|---|--------|-----------|
| 1 | Durable Workflow Engine | LangGraph + Postgres checkpointer |
| 2 | State & Checkpointing | idempotency keys, crash-safe resume |
| 3 | Tool Router / Registry | MCP-native, retries, risk tiers |
| 4 | Agent Memory | episodic / semantic / procedural (pgvector + Postgres) |
| 5 | Human Approval (HITL) | risk-gated `interrupt()`, EU AI Act Art. 14 |
| 6 | Observability | OpenTelemetry GenAI semantic conventions |
| 7 | Evaluation | offline evals, CI regression gate |
| 8 | Governance & Audit | append-only audit log, full replay |

## The applications

Every app shares the same runtime — each one is chosen to stress a distinct runtime
capability: HR agent, Finance agent, IT Ops, Customer Support, SWE agent, Healthcare
referral, Recruiting, Research, and more. Roadmap in [PHASE.md](PHASE.md).

## Status

Phase 1 (runtime core) — in progress. The acceptance test: an agent run survives
`kill -9` mid-execution and resumes exactly where it stopped, with no duplicated side
effects.

## Docs

- [ENTERPRISE.md](ENTERPRISE.md) — runtime architecture (source of truth)
- [PHASE.md](PHASE.md) — roadmap and definitions of shipped
- [CLAUDE.md](CLAUDE.md) — engineering rules and session protocol
- [MEMORY.md](MEMORY.md) — session continuity log

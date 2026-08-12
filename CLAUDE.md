# OpenAgentOS

An open-source enterprise runtime for autonomous agents: durable execution, checkpoint
recovery, human approval, agent memory, observability, evaluation, audit, and replay —
plus enterprise applications (HR, Finance, IT Ops, Support, …) built on that shared
runtime. Built for engineers who need agents that operate businesses, not demos.

## Session protocol (every session, in order)

1. Read `MEMORY.md` — current state, active decisions, next steps.
2. Check `PHASE.md` — what phase we're in and what "shipped" means for it.
3. Consult `ENTERPRISE.md` when touching runtime architecture — it is the source of truth.
4. Before ending: update `MEMORY.md` (what shipped, new decisions, next steps).

## Tech stack (pinned — change only via an Active Decision in MEMORY.md)

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Workflow engine | LangGraph (StateGraph) + PostgresSaver checkpointer |
| Tools | MCP (2026-07-28 spec: stateless core, Tasks, authorization) |
| State / audit / semantic memory | PostgreSQL |
| Episodic memory / vectors | pgvector |
| Cache / queues | Redis |
| Observability | OpenTelemetry GenAI semantic conventions; Langfuse as viewer |
| API layer | FastAPI |
| Local dev | Docker Compose (postgres, redis) |
| Tests | pytest |

Deferred deliberately (see ENTERPRISE.md "Deferred" for triggers): Temporal backend,
Kubernetes, multi-tenant RBAC.

## Repo layout

```
runtime/      # the OS: engine, state, tools, memory, approval, otel, evals, audit
apps/         # enterprise apps built on runtime/ (hr/, finance/, itops/, ...)
docs/         # architecture notes, blog drafts
benchmarks/   # eval sets and benchmark harnesses
```

## Engineering rules

- Smallest working vertical slice first; wire end-to-end before widening.
- Stdlib or an already-installed dependency before any new dependency.
- No abstraction until a second consumer exists (the Temporal backend interface waits
  until Temporal is actually added).
- Every non-trivial module ships with one runnable check (pytest test or `__main__`
  self-check) — unfinished without it.
- TDD for non-trivial logic: failing test → minimal implementation → refactor.
- Files < 800 lines; functions < 50 lines; split when exceeded.
- No hardcoded secrets — env vars only, validated at startup.
- Every external side effect (tool call, payment, ticket) carries an idempotency key.
- Immutable state updates in workflow code — LangGraph reducers, never in-place mutation.

## Definition of done (per feature)

Code + test + one-paragraph doc (in the module docstring or `docs/`) + `MEMORY.md`
updated. A feature nobody can demo or resume after a crash is not done.

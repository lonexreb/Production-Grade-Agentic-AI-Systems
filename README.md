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

## Quickstart

```bash
docker compose up -d --wait      # postgres (pgvector) + redis + jaeger
uv sync --group dev
uv run pytest                    # engine resume, idempotency, router, approval, audit
uv run python -m apps.demo.crash_demo   # crash mid-run -> watchdog revives -> 1 effect
uv run python -m apps.hr.demo           # payroll change gated on human approval
```

Traces: set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` and open the
Jaeger UI at http://localhost:16686.

### Crash mid-run → watchdog revives → exactly one side effect

![crash-resume demo](docs/media/crash-demo.gif)

### Payroll change pauses for human approval, with audit trail

![HR approval demo](docs/media/hr-demo.gif)

### Memory turns the second invoice into a zero-touch payment

![Finance memory demo](docs/media/finance-demo.gif)

### The failure-recovery ladder: fallback, rollback, escalate

![IT Ops ladder demo](docs/media/itops-demo.gif)

The last command is the Phase 1 acceptance test: it starts an agent run, hard-kills
the process **after** its side effect executes but **before** the node completes
(the worst-case crash window), resumes the same run in a fresh process, and proves
the run finishes with the side effect executed **exactly once**.

## Status

**Phase 1 (runtime core) — shipped.** Durable engine (run/resume/replay/history),
watchdog with run leases (dead runs are detected and revived, not just resumable),
idempotent side effects (claim → execute → record), tool router with risk tiers
and an MCP adapter, OTel GenAI tracing with OTLP export.

**Phase 2 (HR Agent + approval + audit) — shipped (v0.2.0).** First real app:
employee email → intent → policy → payroll change → notification. The payroll
tool is approve-tier — the router refuses it without a granting `Approval`, and
the graph obtains one by pausing at `interrupt()`. Paused runs are fully
checkpointed: they survive restarts and resume from any process (HTTP approval
API included) with the manager's decision. Every consequential event lands in
an append-only audit log whose immutability is enforced by a database trigger,
not convention. CI drills the failure paths: crash during approval wait,
transient and hard payroll-API outages.

**Phase 3 (memory + evaluation + Finance Agent) — shipped (v0.3.0).** Three-tier
agent memory (episodic / semantic / procedural, all Postgres) drives risk-based
approval in the Finance Agent: unknown vendors and fraud histories see a human;
verified vendors under the limit clear on audited policy approval. The memory
benefit is a CI-gated benchmark — human touches drop from 1 to 0 on repeat
invoices — alongside offline eval suites per app
(`python -m runtime.evals benchmarks/<app>`). The Finance Agent shipped without
modifying a line of `runtime/` — the reuse bet, proven.

**Phase 4 (IT Ops Agent + the full recovery ladder) — in progress.** The ladder
(`timeout → retry → fallback → rollback → escalate → resume`) is now entirely
runtime-level: tools declare a `fallback` in their manifest (cycle-guarded, same
kwargs contract), and `compensate_run` gives saga-style rollback over the
side-effect ledger — applied fixes that fail verification are undone, the
`compensated` record kept forever. The IT Ops agent drives it end-to-end:
restart fixes it (zero touches), unreachable device falls back to a profile
reset (zero touches), nothing works → rollback to the byte-identical
pre-incident profile and escalate to a human.

## Docs

- [ENTERPRISE.md](ENTERPRISE.md) — runtime architecture (source of truth)
- [PHASE.md](PHASE.md) — roadmap and definitions of shipped
- [CLAUDE.md](CLAUDE.md) — engineering rules and session protocol
- [MEMORY.md](MEMORY.md) — session continuity log

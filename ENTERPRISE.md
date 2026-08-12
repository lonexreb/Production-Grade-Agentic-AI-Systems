# ENTERPRISE.md — OpenAgentOS Runtime Architecture

Source of truth for the runtime. Eight modules, one shared control flow. Every app in
`apps/` consumes these modules; no app reimplements them.

## Control flow (one run)

```
User request
  → Planner (LLM decides workflow)
  → Workflow Graph (LangGraph StateGraph)
  → per-node: checkpoint → memory recall → tool router → execution → verification
  → risk gate: auto | notify | approve-required (interrupt + resume)
  → audit append
  → response  (replayable from any checkpoint)
```

## Failure-recovery ladder

`timeout → retry (backoff) → fallback tool/model → human escalation → resume from checkpoint`

Every module below states where it sits on this ladder.

## The Bain checklist → module map

| Checklist item | Module |
|---|---|
| State | 2. State & Checkpointing |
| Idempotency | 2 (keys) + 3 (enforcement at tool boundary) |
| Durability | 1. Durable Workflow Engine |
| Tool failures | 3. Tool Router |
| Runtime | 1 + 6 (engine + observability) |
| Control flow | 1 (graph) + 5 (approval gates) |

---

## 1. Durable Workflow Engine

**Purpose:** run agent workflows that survive crashes and resume where they left off.

**Tech:** LangGraph `StateGraph` compiled with `PostgresSaver`. One thread per run
(`thread_id = run_id`). State is saved at every superstep; a killed process resumes by
re-invoking the graph with the same `thread_id`.

**Interface sketch:**
```python
runtime.run(app_graph, input, run_id) -> RunResult   # starts or resumes
runtime.replay(run_id, from_checkpoint=None)          # time-travel / audit replay
runtime.history(run_id) -> list[Checkpoint]
```

**Known limitation (state it in interviews):** LangGraph checkpoints are save-points —
resume is caller-triggered, not supervisor-guaranteed. A watchdog that detects dead runs
and re-invokes them is part of Phase 1. Full durable execution semantics (exactly-once
activities, automatic replay) is what the deferred Temporal backend buys.

**Phase 1 ships:** run/resume/replay/history + crash-resume demo + watchdog.
**Later:** pluggable Temporal backend behind the same `runtime.run` interface.

## 2. State & Checkpointing

**Purpose:** define what state is, so recovery is correct rather than accidental.

- Run state = typed `TypedDict` per app graph, reduced immutably (LangGraph reducers).
- Every side-effecting step records an **idempotency key** (`run_id:node:attempt-scope`)
  in Postgres *before* executing; on resume, completed keys are skipped. This is what
  makes "resume" safe — replaying a payment node must not pay twice.
- Checkpoint tables (LangGraph-managed) + `side_effects` table (ours) live in the same
  Postgres — one backup, one truth.

**Phase 1 ships:** idempotency-key table + skip-on-resume logic + tests proving a
double-invoked node executes its side effect once.

## 3. Tool Router / Registry

**Purpose:** one gateway between agents and the outside world.

**Tech:** MCP-native. Tools are MCP servers; the router is an MCP client that holds a
manifest per tool: name, schema, **auth scope**, **risk tier** (see module 5), timeout,
retry policy.

- Retries with exponential backoff + jitter; retry budget per run.
- Circuit breaker per tool (open after N consecutive failures → fallback or escalate).
- Idempotency keys (module 2) enforced here — the router refuses a completed key.
- All calls traced (module 6) and audited (module 8).

**Phase 1 ships:** router + manifest + retries + one real MCP tool + one fake tool for
tests. **Later:** circuit breaker (add when a flaky tool actually justifies it),
tool-level RBAC.

## 4. Agent Memory

**Purpose:** agents that learn across runs. Standard three-tier taxonomy:

| Tier | Holds | Store |
|---|---|---|
| Episodic | past runs: action, context, outcome | pgvector (embedded summaries) |
| Semantic | facts: user prefs, org policies, domain data | Postgres tables |
| Procedural | learned behavior: prompt/policy revisions | versioned prompt store (Postgres) |

- Write path: post-run summarizer extracts episodic entries + semantic facts.
- Recall path: pre-node retrieval injects top-k relevant memories into context.
- Staleness: memories carry `created_at` + `last_confirmed_at`; recall discounts stale
  entries; contradicted facts are superseded, never edited (append-only, like audit).

**Phase 3 ships this** (not Phase 1 — apps run memory-less first). Evaluate LangMem/Mem0
before hand-rolling; adopt if one fits the schema above.

## 5. Human Approval (HITL)

**Purpose:** the enforcement layer that stops consequential actions before execution.
Regulatory anchor: EU AI Act Article 14 (human oversight, enforceable Aug 2026).

- Every tool carries a **risk tier**: `auto` (just do it), `notify` (do it, tell a
  human), `approve` (block until approved).
- Mechanism: LangGraph `interrupt()` before `approve`-tier nodes → run pauses, is fully
  checkpointed, survives restarts → approval API (`POST /runs/{id}/approve|reject`)
  resumes the thread with the decision in state.
- Approvals record who/when/what into the audit log; rejection routes to a fallback or
  ends the run gracefully.

**Phase 2 ships this** with the HR Agent (payroll actions are the forcing function).

## 6. Observability

**Purpose:** every prompt, tool call, token, retry, and failure is traceable.

**Tech:** OpenTelemetry with GenAI semantic conventions (agent / workflow / tool / model
spans; token-usage and latency metrics). Export OTLP → Langfuse for viewing. Vendor-
neutral spans mean LangSmith/Grafana work without re-instrumentation.

- Span per run → per node → per model call / tool call; attributes include model,
  tokens in/out, cost estimate, retry count, checkpoint id.
- Conventions are still marked experimental upstream — pin the semconv version and
  isolate attribute names in one module (`runtime/otel.py`) so a rename is one diff.

**Phase 1 ships:** tracing on engine + router, cost/token metrics, Langfuse via
docker-compose.

## 7. Evaluation

**Purpose:** know the agent works before and after every change.

- Offline: eval set per app (`benchmarks/<app>/cases.jsonl`) — input, expected outcome,
  scoring mode. Deterministic checks where possible; LLM-as-judge where not.
- Regression gate: evals run in CI; a drop below threshold blocks merge.
- Later: shadow mode (run new version alongside old, compare), online metrics.

**Phase 3 ships** offline + regression gate. Shadow/online: add when there are real
users to shadow.

## 8. Governance & Audit

**Purpose:** answer "who did what, when, and why" for any run, forever.

- Append-only `audit_log` table: run_id, actor (agent|human), event, payload hash,
  timestamp. Never updated, never deleted.
- Replay: any run is reconstructable from checkpoints + audit log (module 1's
  `replay()`).
- Secrets: env only, validated at startup. RBAC: single-role in Phase 2 (approver);
  multi-tenant RBAC deferred.

**Phase 2 ships** audit log + replay-from-audit with the HR Agent.

---

## Deferred (YAGNI, with triggers)

| Item | Add when |
|---|---|
| Temporal execution backend | LangGraph watchdog-resume proves insufficient (missed resumes, exactly-once violations) or an adopter demands it |
| Kubernetes manifests | anything runs outside a single Docker Compose host |
| Multi-tenant RBAC | a second organization uses one deployment |
| Circuit breaker | a real tool flaps in practice |
| Shadow/online evals | real traffic exists |
| Graph-store memory (Neo4j) | relational+vector recall measurably fails on relationship-heavy queries |

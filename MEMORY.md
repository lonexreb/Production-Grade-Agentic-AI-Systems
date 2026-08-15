# MEMORY.md — Session Continuity

Read this first every session. Update it before ending every session.

## Current Phase

Phase 3 — Memory + Evaluation + Finance Agent (see PHASE.md). Core SHIPPED:
three-tier memory, eval harness with CI gates, Finance Agent with the measured
memory benchmark (human touches 1 → 0 on repeat invoices). Zero runtime/
changes for the second app — reuse proven. Remaining: v0.3.0 tag after CI
green; user review of blog draft #3.

## Last Session

- **2026-08-15** — Phase 3 core. runtime/memory.py: episodic (FTS recall now,
  pgvector column ready — embed+backfill when an embedding key exists; note
  Anthropic has no embedding API), semantic (append-only, supersede_fact),
  procedural (versioned prompt_store). Decision: hand-rolled over LangMem/Mem0
  (both impose storage layers + LLM extraction we don't need). apps/finance/:
  parse → verify_vendor (semantic) → fraud_check (episodic) → conditional
  human_gate | policy_approve → pay (approve-tier, execute_once) → record
  (writes memory; rejected vendors NOT remembered). Policy approvals audited as
  policy:verified-vendor-under-limit. runtime/evals.py: generic jsonl runner,
  benchmarks/<app>/harness.run_case(), exit-1 CI gate; hr + finance suites 3/3
  each. Finance demo GIF recorded. Blog draft #3. 30 tests green.

- **2026-08-14 (3)** — Phase 2 SHIPPED (v0.2.0). Blog draft #2 ("HITL that
  survives a restart", docs/blog/). VHS installed via brew; demo GIFs recorded
  (docs/media/crash-demo.gif, hr-demo.gif; tapes committed for re-recording)
  and embedded in README. otel.configure(): console exporter now opt-in via
  OAOS_TRACE_CONSOLE=1 (was flooding demo output); default is record-no-export,
  OTLP when endpoint set. Tagged v0.2.0.
- **2026-08-14 (2)** — Phase 2 completion slice. Failure drills
  (tests/test_hr_failure_drills.py): crash-during-approval-wait (fresh Runtime +
  rebuilt graph resumes from Postgres alone), transient payroll outage (router
  retries, effect exactly once), hard outage (run 'failed', zero changes).
  Engine: pending() exposes the interrupt payload, status() reads runs table.
  runtime/api.py: create_app(build_graph) — GET /runs/{id} (with pending
  question), POST /runs/{id}/approve|reject; 409 on double-answer; served per
  app (apps/hr/api.py, port 8000). Verified LIVE over HTTP: paused in one
  process, approved from the API server process. LLM intent classifier in HR
  agent (ANTHROPIC_API_KEY + llm extra; keyword fallback). 23 tests green.

- **2026-08-14** — Phase 1 polish + Phase 2 core. Approval enforcement in router
  (Approval dataclass; ApprovalRequired raised for approve-tier without grant).
  runtime/audit.py (append-only audit_log; UPDATE/DELETE rejected by pg trigger).
  Engine: 'paused' status when result has __interrupt__; resume(decision=...)
  wraps langgraph Command(resume=...). apps/hr/: intent → policy →
  request_approval → payroll (interrupt() first statement of gated node; effect
  via execute_once) → notify; demo shows approve + reject with audit trails.
  Jaeger in compose (UI :16686, OTLP :4318) — verified traces arrive; chose over
  Langfuse (1 container vs 5; swap when token-cost views matter). Blog draft in
  docs/blog/. CI runs hr demo too. 16 tests green.

- **2026-08-12 (3)** — Completed Phase 1 core. Watchdog (runs table + lease
  heartbeat in engine; Watchdog.dead_runs/revive_dead; crash_demo now recovers via
  watchdog, not manual --resume; OAOS_LEASE_S env). MCP adapter
  (runtime/mcp_adapter.py: mcp_tool() wraps an MCP server tool as a router Tool;
  tested against real mcp-server-time via uvx — note: server pinned `--with mcp<2`,
  its release predates SDK 2.x renames like isError→is_error). OTLP export when
  OTEL_EXPORTER_OTLP_ENDPOINT set. Optional LLM planner in demo (ANTHROPIC_API_KEY
  + `llm` extra; stub otherwise). GitHub Actions CI (pytest + crash demo).
  11 tests green.
- **2026-08-12 (2)** — Phase 1 walking skeleton. Scaffolded pyproject (uv, Python
  3.12+), docker-compose (pgvector postgres on host port 5433, redis on 6380).
  Built runtime/: engine.py (Runtime.run/resume/history/replay on PostgresSaver),
  side_effects.py (claim→execute→record idempotency), tools.py (router with
  timeout/retry/backoff), otel.py (GenAI semconv attrs isolated, console exporter).
  Demo agent (plan→act→verify→respond) + crash_demo.py acceptance test: PASS.
  8 pytest tests green.
- **2026-08-12 (1)** — Project founded. Researched the Aug-2026 agent-infra landscape
  (LangGraph checkpointing, Temporal GA OpenAI-SDK integration, MCP 2026-07-28 spec,
  memory taxonomy, OTel GenAI conventions, EU AI Act Art. 14). Wrote CLAUDE.md,
  ENTERPRISE.md, PHASE.md, MEMORY.md, README.md. Published to GitHub:
  https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems (public, branch main).

## Active Decisions

- **2026-08-12** — LangGraph-first runtime; Temporal deferred behind a trigger
  (ENTERPRISE.md Deferred table). Rationale: shippable Phase 1, watchdog covers the
  resume gap for now.
- **2026-08-12** — MCP-native tool layer (2026-07-28 spec).
- **2026-08-12** — Single Postgres for checkpoints, side-effect keys, audit, semantic
  memory; pgvector for episodic. One backup, one truth.
- **2026-08-12** — MEMORY.md is session continuity only; agent-memory subsystem design
  lives in ENTERPRISE.md §4.

## Next Steps (ordered)

1. Tag v0.3.0 once CI is green on the Phase 3 commit.
2. USER: review blog drafts #1–#3 (docs/blog/) before publishing anywhere —
   publishing platform still undecided.
3. Phase 4 planning: pick next app by what it stresses (PHASE.md table) — IT Ops
   (auto-remediation/rollback) or Customer Support (concurrency → shadow evals)
   are the strongest interview stories.
4. Embedding backfill for episodic memory when an embedding API key is
   configured (OpenAI/Voyage — Anthropic has none); swap recall FTS → pgvector.
5. Persistent MCP session pool in mcp_adapter — only if latency starts to matter.

## Open Questions

- Which real MCP tool for Phase 1's router demo (GitHub? Slack? filesystem)?
- Blog platform for the weekly posts.

## Gotchas

- OTel GenAI semconv is still experimental — pin the version; keep attribute names
  isolated in `runtime/otel.py`.
- LangGraph resume is caller-triggered: without the watchdog, a dead run stays dead.
- Never re-execute a side-effecting node without checking the idempotency table first.

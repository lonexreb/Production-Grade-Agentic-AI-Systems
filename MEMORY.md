# MEMORY.md — Session Continuity

Read this first every session. Update it before ending every session.

## Current Phase

Phase 1 — Runtime Core (see PHASE.md). Modules 1, 2, 3, 6 SHIPPED: crash-resume
acceptance demo passes with watchdog-driven recovery (kill mid-run → lease expires
→ watchdog revives → exactly one side effect).

## Last Session

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

1. Record the crash-resume demo (asciinema/GIF) + Phase 1 blog post draft
   ("Checkpoints are not durable execution").
2. Langfuse in docker-compose as the trace viewer (OTLP endpoint already wired via
   OTEL_EXPORTER_OTLP_ENDPOINT).
3. Persistent MCP session pool in mcp_adapter (current: session per call, ~1s
   overhead) — only if demo latency starts to matter.
4. Start Phase 2: HR Agent skeleton + risk-tier enforcement in the router
   (approve-tier tools currently unenforced — router accepts them; interrupt()
   gating lands with Phase 2).

## Open Questions

- Which real MCP tool for Phase 1's router demo (GitHub? Slack? filesystem)?
- Blog platform for the weekly posts.

## Gotchas

- OTel GenAI semconv is still experimental — pin the version; keep attribute names
  isolated in `runtime/otel.py`.
- LangGraph resume is caller-triggered: without the watchdog, a dead run stays dead.
- Never re-execute a side-effecting node without checking the idempotency table first.

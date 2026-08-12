# MEMORY.md — Session Continuity

Read this first every session. Update it before ending every session.

## Current Phase

Phase 1 — Runtime Core (see PHASE.md). Not started; repo contains steering docs only.

## Last Session

- **2026-08-12** — Project founded. Researched the Aug-2026 agent-infra landscape
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

1. Scaffold: `pyproject.toml`, `runtime/`, `docker-compose.yml` (postgres/pgvector,
   redis, langfuse).
2. Walking skeleton: 4-node LangGraph graph + PostgresSaver, `run/resume` working.
3. Idempotency-key table + skip-on-resume, with the double-run test (TDD).
4. Crash-resume demo (`kill -9` mid-run → resume → verify).

## Open Questions

- Which real MCP tool for Phase 1's router demo (GitHub? Slack? filesystem)?
- Blog platform for the weekly posts.

## Gotchas

- OTel GenAI semconv is still experimental — pin the version; keep attribute names
  isolated in `runtime/otel.py`.
- LangGraph resume is caller-triggered: without the watchdog, a dead run stays dead.
- Never re-execute a side-effecting node without checking the idempotency table first.

# MEMORY.md — Session Continuity

Read this first every session. Update it before ending every session.

## Current Phase

Phase 1 — Runtime Core (see PHASE.md). Not started; repo contains steering docs only.

## Last Session

- **2026-08-12** — Project founded. Researched the Aug-2026 agent-infra landscape
  (LangGraph checkpointing, Temporal GA OpenAI-SDK integration, MCP 2026-07-28 spec,
  memory taxonomy, OTel GenAI conventions, EU AI Act Art. 14). Wrote CLAUDE.md,
  ENTERPRISE.md, PHASE.md, MEMORY.md.

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

1. `git init` + first commit of the four docs (offer to push to GitHub).
2. Scaffold: `pyproject.toml`, `runtime/`, `docker-compose.yml` (postgres/pgvector,
   redis, langfuse).
3. Walking skeleton: 4-node LangGraph graph + PostgresSaver, `run/resume` working.
4. Idempotency-key table + skip-on-resume, with the double-run test (TDD).
5. Crash-resume demo (`kill -9` mid-run → resume → verify).

## Open Questions

- Which real MCP tool for Phase 1's router demo (GitHub? Slack? filesystem)?
- Blog platform + repo name availability check for "OpenAgentOS" on GitHub/PyPI.

## Gotchas

- OTel GenAI semconv is still experimental — pin the version; keep attribute names
  isolated in `runtime/otel.py`.
- LangGraph resume is caller-triggered: without the watchdog, a dead run stays dead.
- Never re-execute a side-effecting node without checking the idempotency table first.

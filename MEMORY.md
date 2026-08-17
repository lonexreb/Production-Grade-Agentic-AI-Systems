# MEMORY.md — Session Continuity

Read this first every session. Update it before ending every session.

## Current Phase

Phase 4 — one app per slice. 4a (IT Ops, v0.4.0), 4b (Support, v0.5.0), and 4c
(SWE agent, v0.6.0) SHIPPED. Keys LIVE in .env (gitignored): ANTHROPIC_API_KEY
+ OPENROUTER_API_KEY ($30 lifetime limit, verified, not yet wired into
runtime/llm.py). Both keys were pasted in chat — REMIND USER to rotate them
(console.anthropic.com / openrouter.ai keys page) when convenient. Remaining
apps: Healthcare, Recruiting, Research, CTO, Exec — pick by demand.

## Last Session

- **2026-08-16 (2)** — Phase 4c: SWE agent (flagship). Key saved to .env,
  verified live. apps/swe/: issue → plan (LLM) → code (LLM full-file rewrite)
  → test (real pytest, subprocess, per-run workspace copied from
  sample_project, git init baseline) → bounded retry (MAX_CODE_ATTEMPTS=3,
  gives up honestly) → review (LLM reads git diff) → merge gate (interrupt
  with diff+review) → merge (approve-tier, execute_once, commit + patch file)
  → episodic write. First live run: fixed divide() on attempt 1, reviewer
  flagged float-comparison nuance unprompted. e2e test skipif no key (CI has
  none → skips; HR/demo LLM paths fall back). workspace/ gitignored. GIF.
  Blog draft #6. 42 tests green locally (LLM paths live).

- **2026-08-16** — Phase 4b: Customer Support. FOUND+FIXED real bug: 8-way
  concurrency stress test deadlocked Postgres — every ensure_schema re-ran
  constraint-swap/trigger DDL (ACCESS EXCLUSIVE) concurrently. Fix:
  runtime/schema.apply_once (per-process memo + pg_advisory_xact_lock) for all
  module DDL, and engine._setup_saver gates LangGraph saver.setup() the same
  way. runtime/shadow.py: ShadowRouter (records to shadow_calls, answers from
  stubs, approval gates still enforced, real fns unreachable), shadowed()
  swaps a module's router by convention, compare() diffs observations.
  apps/support/: refunds policy<50/human/repeat-refunder-gated (episodic), KB
  from semantic memory; build_graph(run_id, refund_limit=...) parameterizes
  policy so candidate=same code. Demo prints shadow policy-impact table
  ($75: human gate -> auto at limit 100). Evals 4/4. GIF. Blog draft #5.
  41 tests.

- **2026-08-15 (2)** — Phase 4a: IT Ops. Runtime: Tool.fallback (router routes
  to fallback after retry exhaustion; same-kwargs contract; _tried frozenset
  guards cycles) + side_effects.compensate_run(run_id, handlers) — saga
  rollback in reverse done_at order, rows flip to 'compensated' (status CHECK
  extended via idempotent constraint swap), no-handler effects skipped
  deliberately. apps/itops/: runbook from prompt_store (version audited) → fix
  via execute_once (restart_vpn -> fallback reset_profile) → verify →
  rollback → escalate interrupt → resolve; simulated fleet in device_state
  (reachable/fixable_by decide outcomes). Demo GIF (3 ladder endings). Evals
  3/3 incl. profile-restored-byte-identical assert. Blog draft #4. 35 tests.
- **2026-08-15 (1)** — Phase 3 SHIPPED (v0.3.0). Memory + evals + Finance.

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

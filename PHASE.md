# PHASE.md — OpenAgentOS Roadmap

Module numbers refer to ENTERPRISE.md. Every phase ends with a working demo, a blog
post, and a tagged OSS release — a phase without all three is not shipped.

## Weekly cadence (all phases)

One production feature. One blog post. One benchmark or demo. Update MEMORY.md.

---

## Phase 1 — Runtime Core (weeks 1–8) ← CURRENT

**Goal:** an agent run that survives `kill -9` and resumes exactly where it stopped.

**Ships:** modules 1, 2, 3, 6 (minimal)
- LangGraph engine + PostgresSaver: `run / resume / replay / history` (module 1)
- Watchdog that detects dead runs and re-invokes them (module 1)
- Idempotency-key table + skip-on-resume; test proving one side effect on double-run (module 2)
- MCP tool router with manifest, timeouts, retry/backoff; 1 real + 1 fake tool (module 3)
- OTel GenAI tracing on engine + router → Langfuse; token/cost metrics (module 6)
- Docker Compose: postgres (pgvector image), redis, langfuse
- Walking-skeleton demo agent: 4-node graph (plan → tool → verify → respond)

**Definition of shipped:** recorded demo of crash-mid-run → resume → correct final
output with no duplicated side effect. Blog: "Checkpoints are not durable execution —
building resume that's actually safe."

**Non-goals:** memory, approval, evals, any real app, Temporal, Kubernetes.

## Phase 2 — HR Agent + Approval + Audit (weeks 9–16)

**Goal:** the Bain/Srikanth interview scenario, production-grade, on the runtime.

**Ships:** modules 5, 8 + `apps/hr/`
- Flow: employee email → intent detection → policy retrieval → payroll API (mock MCP
  server) → identity check → **human approval** → audit → notification
- Risk tiers on all tools; `interrupt()` + approval API; approvals audited (module 5)
- Append-only audit log; replay any run from audit + checkpoints (module 8)
- Failure drills: tool timeout, payroll API down, approval rejected, crash during
  approval wait — each recovers per the ladder

**Definition of shipped:** end-to-end demo including a rejected approval and a
crash-during-pause resume. Blog: "Human-in-the-loop that survives a restart."

**Non-goals:** real payroll integration, memory, multi-app reuse claims.

## Phase 3 — Memory + Evaluation + Finance Agent (weeks 17–24)

**Goal:** agents that learn across runs, and proof the runtime is reusable.

**Ships:** modules 4, 7 + `apps/finance/`
- Episodic (pgvector) + semantic (Postgres) + procedural (versioned prompts) memory;
  write/recall/staleness per ENTERPRISE.md §4
- Offline eval sets for HR + Finance; CI regression gate (module 7)
- Finance flow: invoice → OCR → vendor verification → fraud check → approval →
  payment → ledger → audit — **reusing** engine, router, approval, audit unchanged

**Definition of shipped:** benchmark showing memory measurably improves task success on
repeat scenarios; Finance app diff is app code only, zero runtime forks.

## Phase 4+ — One app per ~4 weeks

Each app is chosen to stress one runtime capability, so every app funds a runtime
improvement:

| App | Uniquely stresses |
|---|---|
| IT Ops agent | auto-remediation with rollback; escalation ladder |
| Customer Support agent | high-volume concurrency; online metrics (unlocks shadow evals) |
| SWE agent (issue → PR) | long-running runs; sandboxed execution |
| Healthcare referral agent | strict audit/compliance; PHI handling patterns |
| Recruiting agent | multi-day paused workflows (scheduling loops) |
| Research scientist agent | multi-agent orchestration on one graph |
| Startup CTO agent | composition of other apps as sub-graphs |
| Personal executive agent | cross-tool identity + personal-data memory |

Order is negotiable; pick by demand/interview relevance at the time. Temporal backend,
Kubernetes, and multi-tenant RBAC enter here when their ENTERPRISE.md triggers fire.

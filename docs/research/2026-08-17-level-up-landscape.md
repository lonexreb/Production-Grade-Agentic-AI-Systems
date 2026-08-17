# Level-Up Landscape: Where the Frontier Is (Aug 2026) and Where We Stand

Research pass across enterprise AIOps, agent-reliability research, interop
protocols, and durable-execution infrastructure. Sources linked inline.

## The headline finding: ITBench

[ITBench](https://github.com/itbench-hub/ITBench) (IBM Research, open source)
benchmarks AI agents on **94 real IT-automation scenarios** across SRE,
CISO/compliance, and FinOps. In May 2026, Artificial Analysis + IBM launched
[ITBench-AA](https://artificialanalysis.ai/evaluations/itbench-aa) — and the
numbers are brutal: **every frontier model scores below 50% on SRE tasks;
agents resolve only 13.8% of SRE scenarios, 25.2% of CISO, 0% of FinOps.**

That is an open, public bar sitting embarrassingly low — and our IT Ops agent
already has the exact machinery the benchmark rewards: runbook procedures,
verification-before-resolve, fallback, rollback, and honest escalation.
Entering it turns "production-grade" from a claim into a leaderboard number.

## Enterprise AIOps: where the market went

- Gartner renamed the category to Event Intelligence; the market is
  [$11.16B in 2026 → $32.5B by 2029](https://www.augmentcode.com/guides/what-is-aiops).
- The frontier products ([Datadog Bits AI SRE, PagerDuty AI SRE,
  LogicMonitor](https://openobserve.ai/blog/top-10-aiops-platforms/)) converge
  on: alert correlation → contextual investigation → **governed** automation →
  learn from every incident. "Fully autonomous remediation remains
  aspirational" — the winning posture is exactly our ladder (auto where safe,
  human where not, rollback always possible).
- What they have that we don't: **real telemetry ingestion** (alerts, traces,
  topology as agent inputs) and **learning from incident history** at scale.

## Reliability research: governance is going runtime and path-level

- [AgentSpec (ICSE 2026)](https://cposkitt.github.io/files/publications/agentspec_llm_enforcement_icse26.pdf):
  customizable runtime enforcement rules for agents — a DSL over agent steps.
- [Runtime Governance for AI Agents: Policies on Paths](https://arxiv.org/html/2603.16586v1):
  policies over *sequences* of actions, not single calls. Our risk tiers are
  per-tool and static; the frontier is "a refund after a fraud flag requires a
  human regardless of amount" — path-aware, enforced in the runtime.
- A 2026 KPMG survey: **75% of large-enterprise leaders cite security,
  compliance, auditability as the #1 agent-deployment requirement** — our
  audit/approval/replay story is aimed at exactly this; path-level policy
  enforcement is the missing rung.

## Interop: A2A joined MCP as the second protocol layer

[A2A v1.0.0 (Jan 2026, Linux Foundation)](https://www.mindstudio.ai/blog/six-agent-protocols-ai-builders-2026)
— signed Agent Cards, standardized discovery/delegation; [150+ orgs in
production, integrated into AWS/Azure/GCP](https://atlan.com/know/multi-agent-system-orchestration/).
The 2026 consensus stack: **MCP for agent↔tool, A2A for agent↔agent.** We are
MCP-native already; we have five domain agents and no standard way for them to
delegate to each other. A2A is how the original "Startup CTO orchestrator"
vision becomes real without inventing a proprietary protocol.

## Durable execution: our deferred trigger has fired

[Temporal raised $300M at $5B (Feb 2026); 1.86T actions from AI-native
companies](https://agentmarketcap.ai/blog/2026/04/10/durable-agent-execution-production-temporal-modal-event-sourced).
The ecosystem's verdict: [durable execution is "no longer optional
infrastructure but a baseline requirement," and **LangGraph + Temporal is the
common production stack** — LangGraph for micro-level reasoning flow, Temporal
for macro-level durability](https://cordum.io/blog/temporal-vs-langgraph).
ENTERPRISE.md deferred Temporal behind a trigger ("ecosystem demand");
that trigger has matured. The pluggable backend earns its interface now.

## Online evaluation: shadow was step one

The 2026 practice is [progressive rollout with automated evaluation at each
stage and automatic rollback on degradation](https://mlflow.org/articles/what-is-canary-deployment-ai) —
[evaluation probes running during live inference, not just pre-deployment](https://uptimerobot.com/knowledge-hub/monitoring/ai-agent-monitoring-best-practices-tools-and-metrics/).
We have offline evals (CI-gated) and shadow replay; the missing piece is
canary: route N% of live runs to a candidate policy/build, compare metric
streams, auto-rollback. Our Support app's parameterized graph builder is
already shaped for this.

## Gap analysis

| Frontier capability | We have | Gap |
|---|---|---|
| Durable execution + supervisor resume | ✅ engine + watchdog | Temporal backend (trigger fired) |
| Governed automation, audit, HITL | ✅ modules 5/8 | path-level policies (AgentSpec-style) |
| Offline + shadow evaluation | ✅ module 7 + shadow | online canary + auto-rollback |
| MCP tool layer | ✅ adapter | A2A agent↔agent layer |
| AIOps remediation ladder | ✅ IT Ops app | real telemetry in; **public benchmark score** |
| Memory (episodic/semantic/procedural) | ✅ module 4 | embedding recall (needs key); learning from incident history |

## Recommended Phase 5 (ordered by leverage)

1. **ITBench entry** — flagship. Wire the IT Ops agent to ITBench's SRE
   scenarios (alerts/traces/topology in, diagnosis + remediation out). The
   public bar is 13.8%; any credible score is a headline, and a failed attempt
   still yields the best possible test data for the ladder.
2. **Canary mode** (small) — extend shadow to progressive live rollout with
   auto-rollback; completes module 7's roadmap.
3. **Path-level policy engine** (medium) — risk tiers become rules over run
   history ("post-fraud-flag ⇒ human, any amount"), enforced in the router
   with the audit trail as the evidence stream. Directly addresses the KPMG
   75% and EU AI Act Art. 14.
4. **A2A layer** (medium) — expose apps as A2A agents with signed cards; build
   the CTO orchestrator as an A2A client delegating to HR/Finance/ITOps/
   Support/SWE.
5. **Temporal backend** (large) — pluggable engine backend per the original
   ENTERPRISE.md interface; positions the runtime as "LangGraph + Temporal,
   correctly assembled."

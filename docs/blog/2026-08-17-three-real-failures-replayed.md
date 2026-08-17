# Three Real Agent Failures, Reproduced and Fixed

*People are hitting these in production right now. Here's each one replayed —
bug first, then the fix — as runnable code. (DRAFT)*

Agent-infrastructure writing loves hypotheticals. These three aren't
hypothetical: each is a problem real developers reported publicly in the last
few months. For each, the repo now contains a runnable scenario
(`examples/live_problems/`) that **reproduces the reported bug first**, then
fixes it with the runtime — and CI runs both halves on every push.

---

## 1. "My side effect ran twice after interrupt()" — LangGraph's HITL double-execution

**The report.** A LangChain forum thread ([*Twice execution of agent when using
the interrupt*](https://forum.langchain.com/t/twice-execution-of-agent-when-using-the-interrupt/2964))
and a widely shared write-up ([*LangGraph's HITL Has a Double Execution
Problem*](https://blog.raed.dev/posts/langgraph-hitl/)) describe the same trap:
`interrupt()` works by re-running the node it was called from. Any side effect
placed *before* the interrupt executes **again** when the human answers —
duplicate records, double writes.

**Reproduced.** The naive node — insert a row, then ask for approval — writes
**2 rows for one approved action** on this very runtime. The bug is real and
it's framework-level.

**Fixed.** Two disciplines, both mechanical:
- `interrupt()` is the **first statement** of the gated node, so re-execution
  replays nothing else;
- the effect sits behind an idempotency key (`execute_once`), so even when a
  node does re-run, the ledger returns the stored result instead of executing.

Same framework, same interrupt: **1 row.** Every approval gate in OpenAgentOS
(payroll, payments, merges, escalations) is built this way, and CI's
crash-during-approval-wait drill exists precisely because this class of bug is
invisible until a human takes their time answering.

![HITL double execution](../media/p1-hitl-double-execution.gif)

---

## 2. "My agent charged the customer twice" — the retry double-charge

**The report.** A developer on r/AI_Agents described their fulfillment agent
double-triggering a Printify order because the confirmation arrived during a
retry window. The canonical variant is the [Stripe timeout
double-charge](https://www.channel.tel/blog/idempotent-tool-calls-agent-retry-safety):
the charge **commits server-side**, the response is lost, the retry charges
again. As [another write-up](https://www.buildmvpfast.com/blog/idempotent-ai-agent-retry-safe-patterns-production-workflow-2026)
notes, this never surfaces in testing — test networks are reliable; production
networks bite at the worst moment.

**Reproduced.** A fake provider that commits the charge and *then* times out.
Naive retry: **customer charged twice for one order.**

**Fixed.** Retrying is correct — the router should retry. What's missing is a
key. The runtime's side-effect key is deterministic
(`run_id:node:scope` — stable across retries by construction), and it's
forwarded to the provider as *its* idempotency key. The retry still hits the
provider — and the provider dedupes it: **charged once.** One key, two jobs:
skip-on-resume in our ledger, dedupe-on-retry at the provider.

![retry double charge](../media/p2-retry-double-charge.gif)

---

## 3. "It crashed at item 37 and started over from 1" — the memory-only agent

**The report.** The pattern shows up across dev.to and engineering blogs
([*Your AI Agent Crashed at Step 47. Now What?*](https://dev.to/george_belsky/your-ai-agent-crashed-at-step-47-now-what-41mb),
[*Your AI Agent Just Lost 3 Hours of Work*](https://klementgunndu1.hashnode.dev/your-ai-agent-just-lost-3-hours-of-work-heres-why)):
an agent researching 50 companies makes it through 37, burns $14 in tokens, the
server restarts — and it starts over from company 1, re-spending money on work
it already did. State lived in process memory; the process died; the state died.

**Reproduced and fixed in one run.** A 50-item batch on the runtime processes
one item per graph superstep — which means one checkpoint per item, for free.
The process is hard-killed at item 37. A **fresh process** resumes from the
checkpoint, continues at 37, finishes all 50. Every item processed exactly
once; **$0.00 re-spent** (the memory-only version re-spends $10.80 at
$0.30/item).

The point isn't the loop — it's that nobody wrote checkpointing code. Structure
the work as graph steps and durability is a property of the runtime, not a
feature you remember to add.

![crash at step 37](../media/p3-crash-at-step-37.gif)

---

## The common thread

None of these fixes is clever. They're the same three primitives every case in
this series keeps landing on:

| Reported failure | Primitive |
|---|---|
| interrupt() re-runs my side effect | gate-first nodes + `execute_once` ledger |
| retry double-charged the customer | deterministic keys, forwarded to the provider |
| crash lost 37 items of progress | checkpoint-per-step + supervisor resume |

Every scenario in `examples/live_problems/` asserts both halves — the bug
reproduces AND the fix holds — and runs in CI on every push. If a framework
update ever reintroduces one of these failure modes, a build goes red.

Code: https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems

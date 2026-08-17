# An SWE Agent on Runtime Rails

*The flagship app: LLM-written code, real tests, human-gated merges — OpenAgentOS Phase 4c. (DRAFT)*

Autonomous coding agents are the loudest corner of the ecosystem, and the
demos share a shape: model writes code, confetti. The interesting engineering
is everything around that moment — and it's exactly what a runtime built for
payroll changes and invoice payments already had.

## The loop is a graph with a budget

issue → plan → code → **test** → back to code if red (bounded) → review →
**human merge gate** → merge.

The tester isn't an LLM judging vibes: it runs the project's actual pytest
suite in an isolated per-run workspace and feeds the failure tail back into
the next coding attempt. Three strikes and the run *gives up honestly* —
"escalating to a human engineer" is a successful outcome for an agent;
infinite retry loops are not. In the demo, the sample issue (implement
`divide()` with zero-handling; two tests genuinely failing) goes green on
attempt one, and the LLM reviewer volunteers a real observation about float
comparison edge cases before any human looks at it.

## Everything learned on boring apps transfers

- **Merge is approve-tier.** The same router that refuses an unapproved
  payroll change refuses an unapproved merge — `ApprovalRequired` is
  model-proof in a way "please ask before merging" never is. The diff, the
  review, and the attempt count arrive in the interrupt payload; the human
  answers over the same approval API as HR, Finance, IT Ops, and Support.
- **The merge is idempotent.** Crash after committing but before recording,
  resume, and the workspace does not get a duplicate commit — the same
  `execute_once` ledger that stops double payments stops double merges.
- **Long runs are just runs.** Plan-code-test loops with model latency are
  checkpointed at every step; kill the process mid-loop and the watchdog
  revives it where it stopped. Every plan, attempt, test result, review, and
  decision is in the append-only audit log.

## One call site for the model

All LLM access goes through `runtime/llm.py`: one `complete()` function,
traced with token usage per the OTel GenAI conventions, returning `None` when
no key is configured. Every caller has a deterministic fallback, which is why
the CI pipeline — which holds zero secrets — still runs 41 tests, five demos,
and four eval suites; the SWE e2e test skips itself with a reason instead of
faking a coder without a model.

Fifth app. `runtime/` diff for it: zero lines, again.

Code: https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems

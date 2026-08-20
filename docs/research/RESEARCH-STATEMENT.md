# Research Statement — OpenAgentOS

## The thesis

**The reliability of autonomous AI agents is a systems problem, not a models
problem.** An agent earns the right to operate a business — touch payroll,
move money, remediate infrastructure, merge code — not through better prompting
or a bigger model, but through a runtime whose guarantees are *mechanical*:
enforced by exceptions, ledgers, checkpoints, and gates that a language model
cannot talk its way around, and *validated empirically*: every guarantee
demonstrated by a failure that is reproduced first and prevented in CI forever
after.

## The claims, and their evidence

**1. Checkpoints are not durable execution.** A checkpoint is a save-point;
recovery requires a supervisor that detects dead runs and an idempotency ledger
that makes replay safe. *Evidence:* CI hard-kills an agent in the worst-case
window — after the side effect, before the node completes — and proves a fresh
process finishes the run with exactly one effect.

**2. Governance must be enforcement, not instruction.** "Always ask before
paying" is a suggestion to a model; a raised `ApprovalRequired` is not. Human
approval is durable state (a checkpointed pause answerable over HTTP days
later), never a blocked thread. Immutability is a database trigger, not a code
review convention. *Evidence:* CI drills crash-during-approval-wait, rejected
paths, and audit-tamper attempts.

**3. Agent memory is a risk policy, and its value must be measured in both
directions.** Memory that only reduces friction is a fraud vector. *Evidence:*
a CI-gated benchmark shows human touches drop 1→0 on repeat invoices — while
guard cases prove large amounts and fraud histories still see a human, and
rejected counterparties are never remembered as trusted.

**4. Failure recovery is a ladder, and the middle rungs belong to the
runtime.** timeout → retry → fallback (declared in the tool manifest) →
rollback (saga compensation over the effect ledger) → human escalation →
resume. Giving up cleanly is a successful outcome. *Evidence:* an
auto-remediation drill asserts a rolled-back device profile is byte-identical
to its pre-incident state.

**5. A runtime is proven by reuse, and by reality.** Six domain agents — HR,
Finance, IT Ops, Customer Support, SRE, SWE — run on one runtime with zero
forks of the core; each new domain funded a runtime capability rather than a
demo. Reality is the benchmark of last resort: failures real developers
reported publicly are reproduced before they are claimed fixed; the SWE agent's
first contribution is an upstream pull request to someone else's repository;
the SRE agent targets a public benchmark (ITBench) where frontier agents
resolve 13.8% of scenarios.

## The method

Research-informed, evidence-first, adversarially validated:

- **Bug before fix.** No fix is claimed until the failure it prevents is
  reproduced as running code — and both halves stay in CI so regressions are
  visible, not archaeological.
- **Ship the smallest vertical slice, then let contact with reality fund the
  next capability.** Every gap found in a more real environment (a real repo, a
  real cluster, a parallel workload) was mundane — and fixing mundane gaps
  mechanically, under test, is precisely what "production-grade" means.
- **Every claim has a number or a demo**, and the demos are recorded, replayed
  from audit logs, and published.

## The one-sentence version

> Models make agents capable; runtimes make them trustworthy — and
> trustworthiness is built from boring, mechanical guarantees proven by the
> failures they prevent.

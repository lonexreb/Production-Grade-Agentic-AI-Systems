# Agent Memory That Pays for Itself

*Fewer human touches, measured — OpenAgentOS Phase 3. (DRAFT)*

Agent memory has a hype problem. Most write-ups end with "and now the agent
remembers your preferences," which is a feature description, not a result. Here
is a result: **the first invoice from a vendor takes one human approval; the
second takes zero.** That delta is measured in CI on every push.

## Three tiers, three tables

The ecosystem has converged on episodic / semantic / procedural memory, and
after evaluating LangMem and Mem0 (both good; both impose their own storage
layers and LLM extraction pipelines), we hand-rolled thin on the Postgres we
already run:

| Tier | Holds | Finance Agent uses it to |
|---|---|---|
| Episodic | past runs + outcomes | force the human gate when a vendor has fraud history |
| Semantic | durable facts, append-only | remember that a human approved this vendor |
| Procedural | versioned prompts | roll prompt changes with an audit trail |

Two design choices worth stealing. First, semantic facts are **superseded,
never edited** — when the vendor's bank account changes, the old fact stays in
storage with a pointer to its replacement, same philosophy as the audit log.
Second, episodic recall starts as Postgres full-text search: the pgvector
column exists, but embedding APIs cost money and FTS answers "have we seen
fraud from Acme?" today. The upgrade path is a backfill, not a rewrite.

## Memory as a risk policy, not a personality

The Finance Agent's approval routing reads memory the way an underwriter reads
history:

```
unknown vendor            -> human gate
fraud episode on record   -> human gate (even for verified vendors)
amount >= $10,000         -> human gate (always)
verified + clean + small  -> policy approval, zero human touches
```

The policy approval is itself audited — `approval_granted` by
`policy:verified-vendor-under-limit` — so the compliance answer to "who
approved this payment?" is never a shrug. And rejection teaches too: a rejected
vendor is *not* remembered as verified, so their next invoice faces a human
again.

## The benchmark is in CI

The eval harness runs invoice pairs through the real graph — real Postgres,
real checkpoints, real approval gates — and asserts the deltas:

```
[PASS] finance/memory-eliminates-second-touch    touches: 1 -> 0
[PASS] finance/large-repeat-invoice-still-gated  touches: 1 -> 1
[PASS] finance/rejected-vendor-not-remembered    touches: 1 -> 1, payments: 0
```

The second and third cases matter as much as the first: memory that only ever
*reduces* friction is a fraud vector. The benchmark proves memory lowers cost
on the happy path AND refuses to lower the guard everywhere else.

One more thing the Finance Agent proves: it's the second app on the runtime,
and it shipped without touching a line of `runtime/`. Engine, router, approval,
audit, idempotency — all reused as-is. That was the actual bet of building a
runtime instead of a demo.

Code: https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems

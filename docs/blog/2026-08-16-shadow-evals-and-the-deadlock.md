# Shadow Evals Without Traffic (and the Deadlock That Proved the Test Was Real)

*Policy changes evaluated before deployment — OpenAgentOS Phase 4b. (DRAFT)*

The Customer Support agent was picked to stress two things demos never stress:
many runs at once, and the question every operator eventually asks — *"if I
change this policy, what breaks?"* Both produced results worth writing down.

## The concurrency test earned its keep immediately

The stress test is eight support runs in parallel threads, each issuing its own
refund, asserting every run completes and owns exactly one side effect. First
execution: **Postgres deadlock.**

The cause was self-inflicted and instructive. Every module's `ensure_schema`
re-ran idempotent DDL — including `ALTER TABLE ... DROP/ADD CONSTRAINT` swaps
and trigger recreation — on every run. Idempotent, yes. Concurrent, no: those
statements take `ACCESS EXCLUSIVE` locks, and eight processes swapping the same
constraints deadlock. One run at a time, this bug is invisible forever; the
first parallel workload finds it in milliseconds.

The fix is a shared guard: schema setup is memoized per process and serialized
across processes with `pg_advisory_xact_lock`, and LangGraph's own
`saver.setup()` DDL goes behind the same once-per-process gate. A test that
finds a real bug on its first run is a test that was worth writing.

## Shadow mode: evaluate the candidate, touch nothing

The support refund policy auto-clears refunds under $50. Someone will
eventually propose raising it to $100. The wrong way to find out what that does
is production. The usual right way — shadow deployment — assumes traffic you
may not have.

OpenAgentOS shadow mode replays recorded cases through *any* graph build with
the router swapped for a double that **cannot** touch the world: every call is
recorded to a `shadow_calls` table and answered from stubs; the real tool
function is unreachable by construction. Approval gates still enforce — a
candidate that would violate a gate fails in shadow, which is exactly what you
want to know. The demo output is the deployment decision in three lines:

```
    case    baseline ($50)   candidate ($100)
     $15              auto               auto
     $75        human gate               auto
    $250        human gate         human gate
```

Raising the limit converts the $75 tier from human-gated to automatic and
changes nothing else. That's the answer to "what does this policy change do,"
produced with zero side effects, before anyone deploys anything. Because the
graph builder takes the policy as a parameter, baseline and candidate are the
same code at different settings — no forked agent to keep in sync.

## The same gates, the fourth app

Beyond the new machinery, the support agent reuses everything: small refunds
clear on audited policy approval, large ones pause for a human over the same
approval API, and episodic memory gates repeat refunders — a customer with
refund history sees a human even for $10, because memory that only ever
reduces friction is an abuse vector.

Fourth app. Zero lines of `runtime/` forked. Two runtime capabilities funded:
concurrency-safe schema setup and shadow execution.

Code: https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems

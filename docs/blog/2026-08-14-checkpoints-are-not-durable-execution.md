# Checkpoints Are Not Durable Execution

*Building resume that's actually safe — OpenAgentOS Phase 1. (DRAFT)*

Every agent framework demo shows the happy path. Here's the unhappy one that
actually matters in production: your agent calls the payroll API, the pod gets
OOM-killed before the workflow records the result, and Kubernetes restarts it.
What happens next?

With most agent stacks, one of two bad things: the run is simply gone, or it
restarts from the beginning — and pays someone twice.

## Checkpointing gives you a save-point, not recovery

LangGraph's Postgres checkpointer is genuinely good: state is saved at every
superstep, and re-invoking the graph with the same `thread_id` resumes from the
last checkpoint. But two gaps stand between that and durable execution:

1. **Resume is caller-triggered.** A checkpoint sitting in Postgres doesn't
   restart itself. If nothing notices the dead process, the run stays dead.
2. **Resume replays the interrupted node from the top.** Any side effect that
   executed before the crash executes again — unless something stops it.

OpenAgentOS closes both gaps with two boring, load-bearing pieces.

## Gap 1: a watchdog with leases

Every run registers in a `runs` table; the engine heartbeats a lease on a daemon
thread while the graph executes. A killed process stops heartbeating. The
watchdog looks for `status = 'running' AND lease_expires_at < now()` — runs that
claim to be alive but aren't — and re-invokes them from their checkpoint:

```python
wd = Watchdog()
wd.dead_runs()              # ['crash-demo-209462ee']
wd.revive_dead(build_graph) # resumes each from its last checkpoint
```

## Gap 2: idempotency keys, claim → execute → record

Every side effect runs through `execute_once` with a key of
`run_id:node:scope`. First attempt: claim a `pending` row, execute, record
`done` with the result. A replayed node finds the `done` row and gets the stored
result back — the effect does not run twice:

```python
result = execute_once(conn, make_key(run_id, "act"), run_id,
                      lambda: router.call("send_greeting", ...))
```

The nasty case is a crash *between* the effect and the `done` record. That
window is milliseconds wide, but it exists, and pretending otherwise is how
double payments happen. Phase 1 policy: re-execute (at-least-once) with the
ceiling documented; the upgrade path is a per-tool reconciliation hook that asks
the external system "did attempt X land?" before retrying.

## The acceptance test is the story

CI doesn't just run unit tests — it runs the failure:

1. Start an agent run that hard-kills its own process (`exit 137`) immediately
   **after** its side effect executes but **before** the node completes — the
   worst-case crash window.
2. The lease expires. The watchdog detects the dead run and revives it in a
   fresh process.
3. Assert the run completed AND the side effect happened **exactly once**.

```
=== 1. run crash-demo-209462ee with crash injection ===
[demo] simulating hard crash after side effect
process died mid-run, as intended
=== 2. watchdog detects the dead run and revives it ===
dead run detected: crash-demo-209462ee
=== 3. verify exactly one side effect ===
PASS: crashed mid-run, resumed, completed, side effect executed once
```

If your agent framework can't pass this test, it doesn't have durable
execution — it has checkpoints.

Code: https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems

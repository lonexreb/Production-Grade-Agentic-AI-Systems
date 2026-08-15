# The Failure-Recovery Ladder

*Fallback, rollback, escalate — as runtime features, not app code — OpenAgentOS Phase 4. (DRAFT)*

"The agent retries on failure" is where most agent frameworks stop. Retry is
the first rung of a ladder:

```
timeout -> retry -> fallback -> rollback -> human escalation -> resume
```

The IT Ops agent forced us to build the middle rungs as first-class runtime
features, because auto-remediation is exactly the domain where retrying harder
makes things worse.

## Fallback belongs in the tool manifest

When `restart_vpn` can't reach the device, retrying it three times is three
more timeouts. The right move is a *different* tool — an out-of-band profile
reset that works on unreachable machines. That's a property of the tool
relationship, not of any one agent's prompt, so it lives in the manifest:

```python
Tool(name="restart_vpn", fn=..., fallback="reset_profile")
```

The router exhausts the primary's retry budget, then routes to the fallback —
same kwargs contract, cycle-guarded, traced. Every app on the runtime gets
this rung for one field.

## Rollback is a saga, and honesty is a feature

The nasty scenario: the fallback *applies* (the profile is changed) but
verification says the user still can't connect. Now the device is in a worse
state than when the ticket opened — modified AND broken. Auto-remediation
without undo is how you turn one incident into two.

Every side effect already flows through `execute_once` with an idempotency key
and a stored result. Compensation reuses that ledger: `compensate_run` walks
the run's completed effects in reverse, calls each registered undo handler
with the stored result, and flips the row to `compensated` — the record that
something happened *and was reversed* stays forever, because that's exactly
what an auditor asks about.

Two deliberate choices. Effects without an undo handler are **skipped, not
faked** — not everything is reversible, and a rollback that pretends otherwise
is worse than none. And the `compensated` row keeps its key, so a revived run
can never accidentally re-apply what a human decided to undo.

## Escalation is the ladder's exit, not its failure

After rollback, the agent doesn't loop — it pauses with the full story: what
it tried, what it rolled back, which runbook it followed (pulled from the
versioned prompt store, version audited). The human answers over the same
approval API as every other gate in the runtime, from any process, whenever
they get to it. In the demo, three tickets produce three different endings:

```
restart fixes it            -> resolved, zero human touches
unreachable -> fallback     -> resolved, zero human touches
nothing fixes it            -> rolled back, escalated to tech-north
```

The eval suite pins all three in CI — including asserting the device profile
is byte-identical to its pre-incident value after a rollback. An
auto-remediation agent that can't prove that shouldn't be allowed near a
fleet.

IT Ops is the third app on the runtime. Runtime diff for the app itself: zero
lines. Runtime diff for the new rungs: one field on `Tool`, one function on
the side-effect ledger. That's what "the app funds a runtime improvement"
looks like in practice.

Code: https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems

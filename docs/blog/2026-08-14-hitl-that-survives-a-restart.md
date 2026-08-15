# Human-in-the-Loop That Survives a Restart

*Approval gates as durable state, not blocked threads — OpenAgentOS Phase 2. (DRAFT)*

Most human-in-the-loop demos share an embarrassing secret: the "loop" is a
blocked thread. The agent hits `input()` — or an await on a websocket — and if
the process restarts while the manager is at lunch, the approval request
evaporates. For a payroll change, that's not a UX bug; it's a compliance
incident.

The fix is to stop thinking of approval as *waiting* and start thinking of it
as *state*.

## Enforcement lives in the router, not the prompt

Every tool in OpenAgentOS carries a risk tier: `auto`, `notify`, or `approve`.
The payroll tool is approve-tier, and the router — the single gateway between
agents and the outside world — refuses to execute it without a granting
`Approval`:

```python
router.register(Tool(name="update_payroll", fn=..., risk_tier="approve"))
router.call("update_payroll", ...)          # raises ApprovalRequired
```

This matters because prompt-level guardrails ("always ask before paying") are
suggestions to a language model. A raised exception is not. Under the EU AI
Act's Article 14 (human oversight, enforceable since August 2026), "we asked
the model nicely" is not an oversight mechanism.

## The pause is a checkpoint

When the HR agent reaches the payroll step, the graph calls `interrupt()` with
the approval question. The run stops, its full state checkpoints to Postgres,
and the engine marks it `paused`. There is no blocked thread, no live process,
no lease — the watchdog knows `paused` is not `dead`. The run can sit there for
five seconds or five days.

Answering it is one HTTP call — from any process, on any machine:

```
$ curl localhost:8000/runs/http-4ff005f8
{"run_id": "http-4ff005f8", "status": "paused",
 "pending": {"question": "Approve update_direct_deposit for sam@corp.example?",
             "policy": "Direct deposit changes require manager approval..."}}

$ curl -X POST localhost:8000/runs/http-4ff005f8/approve -d '{"by": "manager@corp.example"}'
{"run_id": "http-4ff005f8", "status": "done",
 "response": "Your update_direct_deposit request was completed."}
```

Under the hood, the decision resumes the LangGraph thread as a
`Command(resume=...)`; the gated node re-executes, `interrupt()` returns the
manager's verdict, and the payroll call runs — through the router, with the
approval attached, guarded by an idempotency key.

## Drill it or it doesn't count

CI runs three adversarial scenarios on every push:

1. **Crash during the approval wait.** A fresh runtime with a rebuilt graph —
   zero shared memory — resumes the paused run from Postgres alone.
2. **Payroll API transiently down.** Two 503s, then success: the router's retry
   budget absorbs the outage and the change lands exactly once.
3. **Payroll API hard down.** Retries exhaust, the run is marked `failed`, and
   the payroll table shows zero changes. Fail closed, not half-done.

And every consequential event — approval requested, granted or rejected, tool
call, notification — lands in an append-only audit log whose immutability is a
Postgres trigger, not a code-review convention. `UPDATE audit_log` raises.
Rejection is a first-class path: declined requests produce zero side effects,
an `approval_rejected` entry, and a notification with the reason.

An approval gate that can't survive a deploy mid-wait isn't a safety
mechanism — it's a demo. Build the pause as state, enforce the gate in the
runtime, and let the humans take their time.

Code: https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems

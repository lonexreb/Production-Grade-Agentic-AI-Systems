#!/usr/bin/env python3
"""Assemble the OpenAgentOS showcase artifact from parts + real Postgres run data."""

import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = json.loads((HERE / "rundata.json").read_text())


def ev(trail, event, actor_startswith=None, nth=0):
    """Find the nth audit event by name (optionally by actor prefix)."""
    hits = [e for e in trail
            if e["event"] == event
            and (actor_startswith is None or e["actor"].startswith(actor_startswith))]
    return hits[nth] if len(hits) > nth else None


def step(node, title, note, audit=None, guarantee=None, html=None):
    s = {"node": node, "title": title, "note": note}
    if audit:
        s["audit"] = audit
    if guarantee:
        s["guarantee"] = guarantee
    if html:
        s["html"] = html
    return s


cases = []

# ---------------- Case 1: crash-resume ----------------
c = DATA["crash"]
se = c["side_effects"][0]
cases.append({
    "id": "crash", "phase": "Phase 1 — runtime core (v0.1.0)", "phase_short": "P1",
    "nav": "Crash → resume, exactly once",
    "title": "Kill the process mid-run. The side effect still happens exactly once.",
    "thesis": "The Phase 1 acceptance test: an agent run is hard-killed (exit 137) "
              "<em>after</em> its side effect executes but <em>before</em> the node completes — "
              "the worst-case crash window. The watchdog revives it; the idempotency ledger "
              "stops the duplicate. This exact scenario runs in CI on every push.",
    "nodes": [
        {"id": "plan", "label": "plan"}, {"id": "act", "label": "act ⚡"},
        {"id": "verify", "label": "verify"}, {"id": "respond", "label": "respond"},
    ],
    "variants": [{"id": "main", "label": "main", "run_id": c["run_id"], "steps": [
        step("plan", "Run starts; every superstep checkpoints to Postgres",
             "The engine registers the run in the <code>runs</code> table and heartbeats a lease "
             "on a background thread. State after each node is durably saved by the LangGraph "
             "Postgres checkpointer.",
             guarantee=["Durable execution", "thread_id = run_id; a fresh process can pick this run up from its last checkpoint at any time."]),
        step("act", "The side effect executes — behind an idempotency key",
             f"Before touching the outside world, the runtime claims key "
             f"<code>{se['key']}</code> as <code>pending</code>, executes, then records "
             f"<code>done</code> with the stored result. That row is the receipt.",
             guarantee=["Idempotency", "claim → execute → record. A replayed node finds the done row and returns the stored result instead of re-executing."]),
        step("act", "💥 kill -9 — the process dies before the node completes",
             "The demo calls <code>os._exit(137)</code> right here. No cleanup handlers run. "
             "The checkpoint for this node was never written, so on resume this node must "
             "re-run from the top — which is exactly the dangerous part.",
             guarantee=["The crash window is real", "the effect happened, the node didn't finish. Naive resume would pay twice; most frameworks do."]),
        step(None, "The lease expires; the watchdog detects a dead run",
             "No process is heartbeating, so <code>lease_expires_at</code> passes. "
             "<code>Watchdog.dead_runs()</code> finds it with "
             "<code>status='running' AND lease_expires_at &lt; now()</code> and re-invokes the graph "
             "in a fresh process — resume is supervisor-guaranteed, not caller-hoped.",
             guarantee=["Supervisor resume", "checkpoints alone are save-points. The watchdog is what turns them into recovery."]),
        step("act", "The node re-runs — and the ledger refuses the duplicate",
             f"execute_once finds key <code>…{se['key'][-14:]}</code> already "
             f"<code>{se['status']}</code> and returns the stored result without calling the tool. "
             f"Database truth: <b>{c['effect_rows']} effect row</b> for this run.",
             guarantee=["Exactly once", f"final state: run status '{c['run_status']}', side-effect status '{se['status']}', effect rows = {c['effect_rows']}."]),
        step("respond", "Run completes as if nothing happened",
             "Verification counts exactly one effect row, the response is produced, and the run "
             "is marked done. Total code an app needs to get all of this: wrap the effect in "
             "<code>execute_once</code>. The runtime does the rest."),
    ]}],
    "footer_html": f"""<div class="takeaway"><b>Why it matters:</b> "the agent retries on failure"
      is easy; <em>not double-charging a customer while retrying</em> is the production problem.
      Run status <span class="chip acc">{c['run_status']}</span> ·
      side-effect key <span class="chip good">{se['status']}</span> ·
      effect rows <span class="chip good">{c['effect_rows']}</span> — queried live from Postgres.</div>""",
})

# ---------------- Case 2: HR approval ----------------
def hr_variant(key, label):
    t = DATA["hr"][key]["trail"]
    rid = DATA["hr"][key]["run_id"]
    req = ev(t, "approval_requested")
    steps = [
        step("intent", "An employee email arrives; intent is classified",
             "“I switched banks — please update my direct deposit.” A light-tier LLM call "
             "(routed to a cheap model via OpenRouter) classifies it; a keyword fallback keeps "
             "CI secret-free.",
             guarantee=["Cost routing", "callers declare tier=\"light\"|\"heavy\", never a vendor. Classification is not a frontier-model problem."]),
        step("policy", "Company policy is retrieved",
             "Direct-deposit changes require manager approval — so the graph routes toward the gate."),
        step("gate", "The run PAUSES — approval is state, not a blocked thread",
             "LangGraph <code>interrupt()</code> checkpoints the full run and the engine marks it "
             "<code>paused</code>. No live process, no lease. The manager can answer in five "
             "seconds or five days, over HTTP, from any machine.",
             audit=req,
             guarantee=["Durable HITL", "CI drills crash-during-approval-wait: a fresh process resumes this run from Postgres alone."]),
    ]
    if key == "approved":
        gr = ev(t, "approval_granted")
        tc = ev(t, "tool_call")
        steps += [
            step("gate", "The manager approves — the decision resumes the graph",
                 f"<code>{gr['actor']}</code> answers via the approval API. The decision arrives as "
                 "a LangGraph <code>Command(resume=…)</code>; the gated node re-runs and "
                 "<code>interrupt()</code> returns the verdict.", audit=gr,
                 guarantee=["Audited authority", "who approved, when, and what they saw — in the append-only ledger, forever."]),
            step("payroll", "The payroll change executes — approval enforced by the router",
                 "The tool is <b>approve-tier</b>: the router raises <code>ApprovalRequired</code> "
                 "without a granting Approval. Prompt guardrails are suggestions; raised exceptions "
                 "are not. The effect itself is wrapped in an idempotency key.", audit=tc,
                 guarantee=["Enforcement > prompting", "EU AI Act Art. 14 wants human oversight. “We asked the model nicely” is not an oversight mechanism."]),
            step("notify", "The employee is told the change is done",
                 "A notify-tier tool sends the reply; the event is audited.",
                 audit=ev(t, "notification_sent")),
        ]
    else:
        rj = ev(t, "approval_rejected")
        steps += [
            step("gate", "The manager REJECTS — rejection is a first-class path",
                 f"<code>{rj['actor']}</code> declines (“unverified bank”). The graph routes around "
                 "the payroll node entirely.", audit=rj,
                 guarantee=["Fail closed", "zero payroll rows exist for this run — verified by the eval suite, not by hope."]),
            step("notify", "The employee gets a decline with the reason",
                 "No silent drops: the rejection produces a notification and an audit entry.",
                 audit=ev(t, "notification_sent")),
        ]
    return {"id": key, "label": label, "run_id": rid, "steps": steps}

cases.append({
    "id": "hr", "phase": "Phase 2 — HR agent + approval + audit (v0.2.0)", "phase_short": "P2",
    "nav": "Payroll change, human-gated",
    "title": "A payroll change that cannot happen without a human — even if the server restarts",
    "thesis": "Employee email → intent → policy → payroll → notification. The payroll tool is "
              "approve-tier: the tool router refuses it without a granting Approval, and the run "
              "pauses as <em>durable state</em> until a manager answers over HTTP.",
    "nodes": [
        {"id": "intent", "label": "intent"}, {"id": "policy", "label": "policy"},
        {"id": "gate", "label": "approval ⏸", "gate": True},
        {"id": "payroll", "label": "payroll ⚡"}, {"id": "notify", "label": "notify"},
    ],
    "variants": [hr_variant("approved", "Manager approves"),
                 hr_variant("rejected", "Manager rejects")],
    "footer_html": """<div class="takeaway"><b>Why it matters:</b> most HITL demos are a blocked
      thread that evaporates on deploy. Here the pause is a checkpoint: CI kills the process
      mid-wait and proves a fresh process finishes the approval. Immutability is a Postgres
      trigger — <code>UPDATE audit_log</code> raises an exception.</div>""",
})

# ---------------- Case 3: Finance memory ----------------
def fin_variant(key, label, first):
    t = DATA["finance"][key]["trail"]
    rid = DATA["finance"][key]["run_id"]
    gr = ev(t, "approval_granted")
    tc = ev(t, "tool_call")
    steps = [
        step("verify", "Semantic memory: is this vendor verified?",
             ("No fact exists — this vendor has never been approved by a human." if first else
              "A durable fact exists: <code>vendor: verified</code>, written when a human approved "
              "invoice #1. Facts are append-only — contradicted facts are superseded, never edited."),
             guarantee=["Memory as risk policy", "unknown vendor → human. Verified + small + clean history → policy. Memory reads like an underwriter reads history."]),
        step("fraud", "Episodic memory: any fraud history?",
             "Full-text recall over past run episodes for this vendor. A fraud episode forces the "
             "human gate even for verified vendors — memory that only ever reduces friction is a fraud vector."),
    ]
    if first:
        steps += [
            step("gate", "Unknown vendor → the run pauses for the CFO",
                 "Human touch #1. The same durable-pause machinery as HR.",
                 guarantee=["Measured, not vibes", "the eval harness counts human touches per run — this is the baseline."]),
            step("gate", "CFO approves; the vendor will be remembered",
                 f"<code>{gr['actor']}</code> grants. On completion the agent writes the semantic "
                 "fact — rejected vendors are deliberately NOT remembered.", audit=gr),
        ]
    else:
        steps += [
            step("policy", "No human needed — policy approval, fully audited",
                 f"The gate routes to policy: <code>{gr['actor']}</code> grants automatically for "
                 "a verified vendor under the $10k limit. The approval is still an audit event — "
                 "“who approved this payment?” never gets a shrug.", audit=gr,
                 guarantee=["Human touches: 0", "the CI benchmark asserts touches drop 1 → 0 on repeat invoices — and that big amounts and fraud histories still see a human."]),
        ]
    steps += [
        step("pay", "Payment executes — approve-tier, idempotent",
             "Same enforcement and same exactly-once ledger as everything else.", audit=tc),
        step("record", "The run writes back to memory",
             "An episodic entry (what happened, outcome) and — after a first human approval — the "
             "semantic vendor fact. This is how invoice #2 becomes zero-touch."),
    ]
    return {"id": key, "label": label, "run_id": rid, "steps": steps}

cases.append({
    "id": "finance", "phase": "Phase 3 — memory + evaluation (v0.3.0)", "phase_short": "P3",
    "nav": "Memory: 1 touch → 0 touches",
    "title": "Agent memory that pays for itself — and the CI benchmark that proves it",
    "thesis": "Invoice → vendor check (semantic memory) → fraud check (episodic memory) → "
              "risk-routed approval → payment. First invoice from a vendor: one human approval. "
              "Second: zero. The delta is a CI-gated benchmark, not a claim.",
    "nodes": [
        {"id": "parse", "label": "parse"}, {"id": "verify", "label": "vendor✓ 🧠"},
        {"id": "fraud", "label": "fraud 🧠"}, {"id": "gate", "label": "human ⏸", "gate": True},
        {"id": "policy", "label": "policy✓"}, {"id": "pay", "label": "pay ⚡"},
        {"id": "record", "label": "record 🧠"},
    ],
    "variants": [fin_variant("human", "Invoice #1 — unknown vendor", True),
                 fin_variant("policy", "Invoice #2 — vendor remembered", False)],
    "footer_html": """<div class="takeaway"><b>The benchmark, in CI on every push:</b>
      <span class="chip good">memory-eliminates-second-touch: 1 → 0</span>
      <span class="chip acc">large-repeat-invoice-still-gated: 1 → 1</span>
      <span class="chip acc">rejected-vendor-not-remembered: payments 0</span> —
      the guard cases matter as much as the win: memory lowers cost on the happy path
      and refuses to lower the guard anywhere else.</div>""",
})

# ---------------- Case 4: IT Ops ladder ----------------
def ops_variant(key, label):
    t = DATA["itops"][key]["trail"]
    rid = DATA["itops"][key]["run_id"]
    rb = ev(t, "runbook_selected")
    tc = ev(t, "tool_call")
    steps = [
        step("runbook", "The runbook comes from versioned procedural memory",
             "Pulled from the prompt store; the exact version the agent followed is audited — "
             "“which procedure was in force?” has a queryable answer.", audit=rb),
    ]
    if key == "restart":
        steps += [
            step("fix", "Primary tool works: restart_vpn",
                 "The device is reachable and a restart fixes it.", audit=tc),
            step("verify", "Verification against the real device state",
                 "The fix is confirmed, not assumed."),
            step("resolve", "Ticket resolved — zero human touches",
                 "The incident closes itself; an episodic memory entry records the outcome.",
                 audit=ev(t, "ticket_updated"),
                 guarantee=["Rung 1", "retry was enough. Most tickets should end here."]),
        ]
    elif key == "fallback":
        steps += [
            step("fix", "Primary tool FAILS — the device is unreachable",
                 "restart_vpn raises ConnectionError. Retrying harder is just more timeouts.",
                 guarantee=["Fallback in the manifest", 'Tool(name="restart_vpn", fallback="reset_profile") — the relationship between tools is runtime data, not prompt hope.']),
            step("fix", "The router falls back: reset_profile (out-of-band)",
                 "Same kwargs contract, cycle-guarded, traced. The audit shows which tool actually ran.",
                 audit=tc),
            step("verify", "Verified fixed", "The profile reset worked on the unreachable device."),
            step("resolve", "Resolved — still zero human touches", "",
                 audit=ev(t, "ticket_updated"),
                 guarantee=["Rung 2", "a different tool, not a harder retry."]),
        ]
    else:
        rbk = ev(t, "rollback")
        esc_ = ev(t, "escalation_decided")
        comp = DATA.get("compensated_example") or {}
        steps += [
            step("fix", "Fallback applies a change… ",
                 "reset_profile modifies the device profile (the prior value is captured in the "
                 "stored result — that detail is about to matter).", audit=tc),
            step("verify", "…but verification FAILS",
                 "The user still can't connect. The device is now modified AND broken — worse than "
                 "when the ticket opened. Auto-remediation without undo turns one incident into two."),
            step("rollback", "Saga rollback: the change is undone",
                 f"<code>compensate_run</code> walks the run's completed effects in reverse and calls "
                 f"each undo handler with the stored result. The ledger row flips to "
                 f"<code>{comp.get('status', 'compensated')}</code> and keeps its key forever. The eval "
                 "suite asserts the profile is byte-identical to its pre-incident value.", audit=rbk,
                 guarantee=["Honest reversal", "effects without an undo handler are skipped, not faked — pretending everything is reversible is worse than saying so."]),
            step("escalate", "A human decides what happens next",
                 f"The run pauses with the full story: what was tried, what was rolled back, which "
                 f"runbook was followed. <code>{esc_['actor']}</code> assigns an on-site tech.",
                 audit=esc_,
                 guarantee=["Escalation is the exit", "giving up cleanly is a successful outcome for an agent. Infinite retry loops are not."]),
            step("resolve", "Ticket escalated — with a perfect paper trail", "",
                 audit=ev(t, "ticket_updated")),
        ]
    return {"id": key, "label": label, "run_id": rid, "steps": steps}

cases.append({
    "id": "itops", "phase": "Phase 4a — IT Ops + the recovery ladder (v0.4.0)", "phase_short": "P4a",
    "nav": "Fallback → rollback → escalate",
    "title": "The failure-recovery ladder: three tickets, three different endings",
    "thesis": "timeout → retry → <b>fallback</b> → <b>rollback</b> → escalate → resume. "
              "The middle rungs are runtime features: tools declare fallbacks in their manifest, "
              "and applied fixes that fail verification are undone via saga compensation over the "
              "side-effect ledger.",
    "nodes": [
        {"id": "runbook", "label": "runbook 🧠"}, {"id": "fix", "label": "auto-fix ⚡"},
        {"id": "verify", "label": "verify"}, {"id": "rollback", "label": "rollback ↩"},
        {"id": "escalate", "label": "escalate ⏸", "gate": True}, {"id": "resolve", "label": "resolve"},
    ],
    "variants": [ops_variant("restart", "Restart fixes it"),
                 ops_variant("fallback", "Unreachable → fallback"),
                 ops_variant("rollback", "Nothing works → rollback + human")],
    "footer_html": """<div class="takeaway"><b>Why it matters:</b> an auto-remediation agent that
      can't prove the device profile is byte-identical after a failed fix shouldn't be allowed near
      a fleet. Runtime cost of the two new rungs: one field on <code>Tool</code>, one function on
      the effect ledger.</div>""",
})

# ---------------- Case 5: Support shadow ----------------
sc = DATA["shadow_calls"]
shadow_rows = "".join(
    f"<tr><td>{r['run_id']}</td><td>{r['tool']}</td><td>{json.dumps(r['kwargs'])[:60]}…</td></tr>"
    for r in sc[:4])
cases.append({
    "id": "support", "phase": "Phase 4b — shadow evals + concurrency (v0.5.0)", "phase_short": "P4b",
    "nav": "Shadow evals, zero side effects",
    "title": "“What if we raise the refund limit?” — answered before deployment, touching nothing",
    "thesis": "Shadow mode replays recorded cases through a <em>candidate</em> agent build with the "
              "router swapped for a double that records intent and cannot call real tools. The "
              "policy question becomes a three-line table instead of a production experiment.",
    "nodes": [
        {"id": "intent", "label": "intent"}, {"id": "history", "label": "history 🧠"},
        {"id": "gate", "label": "refund gate", "gate": True},
        {"id": "refund", "label": "refund ⚡"}, {"id": "reply", "label": "reply"},
    ],
    "variants": [{"id": "main", "label": "main", "run_id": sc[0]["run_id"] if sc else "shadow-…", "steps": [
        step("intent", "Recorded cases replay through the REAL graph",
             "Same code, same gates, same memory reads. Only the router is different: a "
             "<code>ShadowRouter</code> double answers from stubs.",
             guarantee=["Suppressed by construction", "the real tool functions are unreachable from shadow — not discouraged, unreachable. Approval gates still enforce."]),
        step("gate", "Baseline policy: $75 refund → human gate",
             "With the auto-refund limit at $50, the $75 case pauses for a human. The graph builder "
             "takes the limit as a parameter — candidate and baseline are the same code at "
             "different settings. No forked agent to drift."),
        step("gate", "Candidate policy ($100 limit): $75 → auto",
             "The candidate clears it on policy approval. $15 behaves identically in both; $250 is "
             "gated in both. That's the entire deployment decision, in one table.",
             html="""<table class="data" style="margin-top:10px"><thead>
               <tr><th>case</th><th>baseline ($50)</th><th>candidate ($100)</th></tr></thead><tbody>
               <tr><td>$15</td><td><span class="chip good">auto</span></td><td><span class="chip good">auto</span></td></tr>
               <tr><td>$75</td><td><span class="chip bad">human gate</span></td><td><span class="chip good">auto</span></td></tr>
               <tr><td>$250</td><td><span class="chip bad">human gate</span></td><td><span class="chip bad">human gate</span></td></tr>
             </tbody></table>"""),
        step("refund", "Every intended call is recorded — none executed",
             "The shadow_calls table holds what the candidate WOULD have done. Real refund rows "
             "created during the whole analysis: zero.",
             html=f"""<table class="data" style="margin-top:10px"><thead>
               <tr><th>shadow run</th><th>intended tool</th><th>kwargs</th></tr></thead>
               <tbody>{shadow_rows}</tbody></table>""",
             guarantee=["Bonus finding", "the 8-way concurrency stress test for this app deadlocked Postgres on its first run — concurrent DDL taking ACCESS EXCLUSIVE locks. Invisible serially, fatal in parallel. Fixed with advisory-lock-serialized schema setup."]),
    ]}],
    "footer_html": """<div class="takeaway"><b>Why it matters:</b> shadow deployment normally
      assumes production traffic. Replaying recorded cases through a router double gives the same
      answer — which cases change outcome and what would have been done differently — with zero
      risk, before anyone deploys anything.</div>""",
})

# ---------------- Case 6: SWE agent ----------------
t = DATA["swe"]["trail"]
plan_e = ev(t, "plan_made")
code_e = ev(t, "code_written")
test_e = ev(t, "tests_run")
rev_e = ev(t, "review_done")
gr_e = ev(t, "approval_granted")
mg_e = ev(t, "tool_call")
def _clean_patch(p):
    """Drop __pycache__/binary diff sections — noise from the workspace commit."""
    out, skip = [], False
    for line in p.splitlines():
        if line.startswith("diff --git"):
            skip = "__pycache__" in line
        if not skip:
            out.append(line)
    return "\n".join(out)

patch = _clean_patch(DATA["swe"].get("patch", ""))
review_text = rev_e["payload"].get("review", "") if rev_e else ""
cases.append({
    "id": "swe", "phase": "Phase 4c — the SWE agent (v0.6.0)", "phase_short": "P4c",
    "nav": "SWE agent, human-gated merge",
    "title": "An LLM writes real code. Real tests judge it. A human owns the merge.",
    "thesis": "issue → plan → code → test (the project's actual pytest suite, in an isolated "
              "workspace) → bounded retry → LLM review → human merge gate → idempotent merge. "
              "Everything below is from a real run: real model output, real test results, real diff.",
    "nodes": [
        {"id": "plan", "label": "plan"}, {"id": "code", "label": "code 🤖"},
        {"id": "test", "label": "pytest"}, {"id": "review", "label": "review 🤖"},
        {"id": "gate", "label": "merge gate ⏸", "gate": True}, {"id": "merge", "label": "merge ⚡"},
    ],
    "variants": [{"id": "main", "label": "main", "run_id": DATA["swe"]["run_id"], "steps": [
        step("plan", "The model plans against the real repo",
             "Issue: implement divide() with ValueError on division by zero — two tests genuinely "
             "failing in the sample project. A light-tier model picks the target file.", audit=plan_e),
        step("code", "Claude writes the full new file into an isolated workspace",
             "Per-run workspace, git-baselined. If a previous attempt failed, the pytest output is "
             "fed back into the next prompt. Three failed attempts → the run gives up honestly and "
             "escalates — infinite loops are not a feature.", audit=code_e),
        step("test", "The judge is pytest, not vibes",
             "The project's real test suite runs in a subprocess. This run: green on attempt 1 — "
             "5 passed, including the two that were failing.", audit=test_e,
             guarantee=["Ground truth", "an LLM opinion never gates progress; a test suite does."]),
        step("review", "An LLM reviews the diff — and finds something real",
             f"Unprompted, the reviewer flagged the float-comparison edge case:<br>"
             f"<em style=\"color:var(--muted)\">“{review_text[:260]}…”</em>", audit=rev_e),
        step("gate", "Nothing merges without a human",
             "The run pauses with the diff, the review, and the attempt count in the interrupt "
             "payload — answered over the same approval API as payroll and payments.", audit=gr_e,
             guarantee=["Same rails as payroll", "the router that refuses an unapproved payment refuses an unapproved merge. ApprovalRequired is model-proof."]),
        step("merge", "The merge commits — exactly once",
             "Idempotency ledger again: crash after committing but before recording, resume, and "
             "there is no duplicate commit. The actual merged diff:", audit=mg_e,
             html=f'<pre class="diff" data-diff-src>{patch.replace("<", "&lt;").replace(">", "&gt;")}</pre>'),
    ]}],
    "footer_html": """<div class="takeaway"><b>Why it matters:</b> autonomous coding demos end at
      “the model wrote code.” Production starts there: isolation, real test gates, bounded
      retries, human-owned merges, idempotent side effects, and a full audit trail — all inherited
      from the same runtime that runs payroll. Fifth app, zero lines of runtime forked.</div>""",
})

# ---------------- assemble ----------------
css = (HERE / "page.css").read_text()
js = (HERE / "page.js").read_text()

modules = [
    ("1", "Durable Workflow Engine", "LangGraph + Postgres checkpointer; watchdog leases"),
    ("2", "State &amp; Checkpointing", "idempotency keys; claim → execute → record"),
    ("3", "Tool Router", "risk tiers, retries, fallbacks, MCP adapter"),
    ("4", "Agent Memory", "episodic / semantic / procedural, all Postgres"),
    ("5", "Human Approval", "interrupt() as durable state; HTTP approval API"),
    ("6", "Observability", "OTel GenAI semconv; token + cost tracing"),
    ("7", "Evaluation", "offline evals, CI gates, shadow mode"),
    ("8", "Governance &amp; Audit", "append-only ledger; immutability by trigger"),
]
modgrid = "".join(
    f'<div class="mod"><span class="mnum">M{n}</span><b>{t_}</b><span>{d}</span></div>'
    for n, t_, d in modules)

html = f"""<meta charset="utf-8">\n<title>OpenAgentOS — Production Agentic AI, Replayed</title>
<style>{css}</style>
<div class="wrap">
<header class="hero">
  <div class="eyebrow">OpenAgentOS · six patterns · real recorded runs</div>
  <h1>Production-grade agentic AI, replayed from the audit log</h1>
  <p class="lede">Every walkthrough below is driven by a <em>real run</em> pulled from the
  runtime's Postgres — actual audit events, timestamps, decisions, and diffs. Step through each
  one to see what the runtime guarantees at every moment: durable execution, exactly-once side
  effects, human approval as state, memory as risk policy, saga rollback, shadow evaluation.</p>
  <div class="statrow">
    <div class="stat"><b>6</b><span>tagged releases</span></div>
    <div class="stat"><b>5</b><span>apps, one runtime</span></div>
    <div class="stat"><b>42</b><span>tests in CI</span></div>
    <div class="stat"><b>0</b><span>runtime forks per app</span></div>
    <div class="stat"><b>1→0</b><span>human touches (memory)</span></div>
  </div>
</header>
<div class="main">
  <nav class="rail" id="rail" aria-label="cases"></nav>
  <section id="stage" class="case active" aria-live="polite"></section>
</div>
<section class="spine wrap-inner">
  <h2>The runtime spine every app shares</h2>
  <div class="modgrid">{modgrid}</div>
</section>
<footer>
  Source, demos (GIFs), eval suites, and CI:
  <a href="https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems">github.com/lonexreb/Production-Grade-Agentic-AI-Systems</a>
  &nbsp;·&nbsp; Built on LangGraph + Postgres, MCP, OpenTelemetry GenAI conventions.
</footer>
</div>
<script>window.OAOS_CASES = {json.dumps(cases)};</script>
<script>{js}</script>
"""

out = HERE / "openagentos-showcase.html"
out.write_text(html)
print(f"built {out} ({len(html):,} chars, {len(cases)} cases)")

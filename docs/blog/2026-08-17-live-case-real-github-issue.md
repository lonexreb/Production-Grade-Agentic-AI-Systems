# Live Case: The SWE Agent Fixes a Real Open GitHub Issue

*Real repo, real issue text, real test suite as the judge — OpenAgentOS in its
own domain. (DRAFT)*

Everything in this series so far ran against fixtures we controlled. This one
doesn't. We pointed the SWE agent at a real open issue in someone else's
repository and let the pipeline run: plan from the issue text as written, edit
the real codebase, judged by pytest, reviewed by a model, merged only through
the human gate.

## The case

[mgomezdev/themis#38](https://github.com/mgomezdev/themis/issues/38): the
backend's API-key auth guards `require_scope()` with

```python
assert scope in SCOPES, f"unknown scope {scope!r}"
```

— the *only* typo guard across 113 call sites. The problem: `assert` is
stripped when Python runs with `-O`. In optimized mode the check silently
vanishes, and a typo'd scope string (`"jobs:reed"`) becomes a dependency that
never validates anything. A classic correctness bug that survives every test
run (nobody tests under `-O`) and every code review (it *looks* like
validation).

## Acceptance criteria first, agent second

Before the agent saw anything, we wrote the acceptance test *from the issue
text* — including the part that makes this issue interesting:

```python
def test_guard_survives_python_O():
    proc = subprocess.run([sys.executable, "-O", "-c",
        "from app.auth import require_scope; require_scope('bogus:scope')"], ...)
    assert proc.returncode != 0   # guard vanished under -O -> still an assert
```

On the unfixed code: **2 of 3 tests fail** — the guard raises the wrong
exception type, and under `-O` it doesn't fire at all. The bug is real and
mechanically demonstrated, not narrated.

## The run

The workspace is assembled from the repo's actual branch (the issue targets
unmerged code — the agent works where the bug lives). The agent gets the issue
text verbatim. What happened, from the audit trail:

- **plan_made** — among the package's real files, it picked `app/auth.py`
- **code_written** — one attempt
- **tests_run** — 3/3 green, including the `-O` subprocess test
- **review_done** — the reviewer independently articulated *why* this matters:
  "`assert` statements are stripped under `python -O`, which would silently
  disable scope validation across all 113 call sites … this is the right
  exception type for a programming error"
- **approval_granted** — the human merge gate; nothing lands without it
- **tool_call** — idempotent merge, patch emitted

The entire diff:

```diff
-    assert scope in SCOPES, f"unknown scope {scope!r}"
+    if scope not in SCOPES:
+        raise ValueError(f"unknown scope {scope!r}")
```

Exactly what the maintainer asked for. Small is the point: the agent didn't
refactor the file, didn't "improve" adjacent code, didn't invent scope
constants. Issue in, minimal reviewed patch out.

![live case](../media/live-case-swe.gif)

## What the real world forced us to fix

Fixtures flatter you; real repos don't. Two agent upgrades came out of contact
with reality, both embarrassingly ordinary:

1. **File discovery was flat.** The planner globbed `*.py` in the workspace
   root — fine for our sample project, blind for any real package layout. Now
   it walks the tree.
2. **Output headroom was demo-sized.** A full-file rewrite of a real module
   needs more than 2k tokens of budget.

That's the recurring lesson of this whole project: every time the runtime
touches a more real environment, the gaps it reveals are mundane — and fixing
them mechanically is what "production-grade" actually means.

The patch sits in the workspace, gate-approved on our side. Proposing it
upstream is a human's call — which is, of course, the design.

Code: https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems

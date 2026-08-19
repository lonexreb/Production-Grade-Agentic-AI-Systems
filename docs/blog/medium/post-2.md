# Medium Post #2 — paste into Medium; upload docs/media/live-case-swe.gif at the marker

# An Autonomous Agent Just Fixed a Real GitHub Issue. A Human Owns the Merge.

## Real repo, real issue text, real test suite as the judge — ending in an upstream pull request.

Every demo of an AI coding agent runs against fixtures the author controls. This one doesn't. I pointed my open-source runtime's SWE agent at a real open issue in someone else's repository and let the pipeline run end to end. Here's exactly what happened — including what reality broke.

## The case

[mgomezdev/themis#38](https://github.com/mgomezdev/themis/issues/38): the backend's API-key auth guards `require_scope()` with

```python
assert scope in SCOPES, f"unknown scope {scope!r}"
```

— the only scope-typo guard across 113 call sites. Python strips `assert` under `-O`: in optimized mode the check silently vanishes, and a typo'd permission scope becomes a dependency that never validates anything. It looks like validation, passes every normal test run, and disappears exactly when optimization is on.

## Proof before the agent

Before the agent saw anything, I wrote the acceptance criteria as tests, from the issue text — including a subprocess test that imports the real module under `python -O` and demands the guard still fire. On the untouched code: **2 of 3 tests fail.** The bug demonstrated mechanically, not narrated.

## The run

*[Insert GIF: live-case-swe.gif]*

The workspace was assembled from the repo's actual branch (the issue targets unmerged code — the agent works where the bug lives). One attempt: the agent picked `app/auth.py` from the real package tree, wrote the fix, and the repo's pytest went 3/3 green — including the `-O` proof. The LLM reviewer, unprompted, articulated exactly why the fix matters: "`assert` statements are stripped under `python -O`, which would silently disable scope validation across all 113 call sites… This is the right exception type for a programming error."

The entire diff:

```diff
-    assert scope in SCOPES, f"unknown scope {scope!r}"
+    if scope not in SCOPES:
+        raise ValueError(f"unknown scope {scope!r}")
```

Small is the point. No refactoring sprawl, no "improvements" to adjacent code. Issue in, minimal reviewed patch out — exactly what the maintainer asked for.

## Nothing merges without a human

The merge is an approve-tier tool behind the same gate my runtime uses for payroll changes and invoice payments: the router refuses it without a granting approval, the decision is audited, and the merge itself is idempotent (crash after committing, resume, no duplicate). Then a human — me — reviewed the patch, adapted the tests to the repo's conventions, ran their full suite before and after (zero regressions), and submitted [pull request #48](https://github.com/mgomezdev/themis/pull/48) with honest provenance: authored by an autonomous agent, reviewed and submitted by a human.

## What reality taught the agent

Fixtures flatter you; real repos don't. Contact with this one repo forced two embarrassingly ordinary upgrades: recursive file discovery (the planner previously only saw the workspace root) and a bigger output budget for real-sized files. That's the recurring lesson of this whole project: every time the runtime touches a more real environment, the gaps it reveals are mundane — and fixing them mechanically, under test, is what "production-grade" actually means.

The same runtime now runs six domain agents — HR, Finance, IT Ops, Customer Support, SRE, and this SWE agent — with zero forks of the core. Code and the full series: [github.com/lonexreb/Production-Grade-Agentic-AI-Systems](https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems)

*Part 2 of a series on production-grade agentic systems. Part 1: three real agent failures — double charges, double writes, lost progress — reproduced and fixed.*

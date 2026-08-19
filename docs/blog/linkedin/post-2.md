# LinkedIn Post #2 — ready to paste

---

I pointed my autonomous SWE agent at a real open GitHub issue in someone else's repo. It's now an upstream pull request.

The issue (themis#38): an API-key auth system guards its permission scopes with `assert scope in SCOPES` — the ONLY typo check across 113 call sites. The trap: Python strips assert statements under -O. In optimized mode, the security check silently vanishes.

How the run went:

🧪 Acceptance tests first — written from the issue text, including a subprocess test under `python -O`. On the untouched code: 2 of 3 failing. The bug proven mechanically, before the agent saw anything.

🤖 One attempt — the agent navigated the real package tree, picked app/auth.py, and wrote exactly the fix the maintainer asked for. The entire diff is 3 lines.

✅ The judge was pytest, not vibes — the repo's real test suite went 3/3 green, including the -O proof.

🔍 The LLM reviewer, unprompted, explained WHY it matters: "assert statements are stripped under python -O, which would silently disable scope validation across all 113 call sites."

🙋 Nothing merged without a human — the same approval gate my runtime uses for payroll changes and payments gates code merges. Then a human (me) reviewed and submitted it upstream, with honest provenance in the PR body.

The part I keep coming back to: contact with ONE real repo forced two embarrassingly ordinary agent upgrades (recursive file discovery, bigger output budgets). Fixtures flatter you. Real repos don't. That gap — found mechanically, fixed under test — is what "production-grade" actually means.

Watch the full run (live terminal recording, real audit trail, the diff):
👉 [YOUR BLOG/ARTIFACT LINK HERE]

The PR: https://github.com/mgomezdev/themis/pull/48
The runtime: https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems

Post #2 in the production-grade agentic systems series. Post #1 covered three real agent failures (double charges, double writes, lost progress) — reproduced and fixed.

#AIAgents #AgenticAI #SoftwareEngineering #OpenSource #LLMOps #AIEngineering

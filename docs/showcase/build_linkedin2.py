#!/usr/bin/env python3
"""Assemble the live-case artifact: SWE agent fixes a real GitHub issue."""

import base64
import json
from pathlib import Path

REPO = Path("/Users/shubh-trips/Documents/personal-project/production-autonomous-ai-agents")
HERE = Path(__file__).parent
DATA = json.loads((HERE / "livecase-data.json").read_text())

gif_b64 = base64.b64encode((REPO / "docs/media/live-case-swe.gif").read_bytes()).decode()
review = next(e["payload"]["review"] for e in DATA["trail"] if e["event"] == "review_done")
test_payload = next(e["payload"] for e in DATA["trail"] if e["event"] == "tests_run")

trail_rows = "".join(
    f'<div class="levent"><span class="t">{e["t"]}</span>'
    f'<span class="actor {"human" if "@" in e["actor"] else ""}">{e["actor"]}</span>'
    f'<span class="ev">{e["event"]}</span></div>'
    for e in DATA["trail"])

css = """
:root {
  --ground:#eef1f4; --surface:#ffffff; --surface2:#e4e9ee; --line:#ccd4dc;
  --text:#1a2229; --muted:#5c6a76; --accent:#b87a1e;
  --accent-soft:rgba(184,122,30,.12); --good:#2e7d5b; --bad:#b04a4a; --info:#3d6fa3;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --display:"Avenir Next",Avenir,Futura,"Century Gothic",system-ui,sans-serif;
  --body:system-ui,-apple-system,"Segoe UI",sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:#101418; --surface:#1a2027; --surface2:#232b34; --line:#2e3944;
    --text:#e8edf2; --muted:#8a96a3; --accent:#e8a33d;
    --accent-soft:rgba(232,163,61,.14); --good:#5fb88a; --bad:#d96a6a; --info:#6aa3d9;
  }
}
:root[data-theme="dark"] {
  --ground:#101418; --surface:#1a2027; --surface2:#232b34; --line:#2e3944;
  --text:#e8edf2; --muted:#8a96a3; --accent:#e8a33d;
  --accent-soft:rgba(232,163,61,.14); --good:#5fb88a; --bad:#d96a6a; --info:#6aa3d9;
}
* { box-sizing:border-box; }
body { margin:0; background:var(--ground); color:var(--text);
       font-family:var(--body); font-size:16px; line-height:1.6; }
a { color:var(--accent); }
.wrap { max-width:860px; margin:0 auto; padding:0 22px; }
header { padding:54px 0 30px; }
.eyebrow { font-family:var(--mono); font-size:12px; letter-spacing:.14em;
           text-transform:uppercase; color:var(--accent); }
h1 { font-family:var(--display); font-weight:700; letter-spacing:-.015em;
     font-size:clamp(30px,6vw,44px); line-height:1.1; margin:10px 0 14px; text-wrap:balance; }
.lede { color:var(--muted); max-width:62ch; }
section { border-top:1px solid var(--line); padding:34px 0 40px; }
h2 { font-family:var(--display); font-size:24px; font-weight:700; margin:0 0 12px;
     letter-spacing:-.01em; }
p { max-width:68ch; }
p.mut { color:var(--muted); }
.codebox { font-family:var(--mono); font-size:13px; background:var(--surface);
           border:1px solid var(--line); border-radius:8px; padding:14px 18px;
           overflow-x:auto; margin:14px 0; white-space:pre; line-height:1.5; }
.codebox .bad { color:var(--bad); } .codebox .good { color:var(--good); }
.codebox .mutid { color:var(--muted); }
.chips { display:flex; gap:10px; flex-wrap:wrap; margin:14px 0; }
.chip { border:1px solid var(--line); background:var(--surface); border-radius:999px;
        padding:6px 16px; font-family:var(--mono); font-size:13px; }
.chip.bad { color:var(--bad); } .chip.good { color:var(--good); }
.chip.acc { color:var(--accent); }
.gifframe { border:1px solid var(--line); border-radius:10px; overflow:hidden;
            background:#1a1d29; margin:16px 0; }
.gifframe img { display:block; width:100%; height:auto; }
.quote { border-left:3px solid var(--accent); background:var(--accent-soft);
         padding:14px 18px; border-radius:0 8px 8px 0; font-size:14.5px;
         max-width:70ch; margin:14px 0; }
.quote b { color:var(--accent); font-family:var(--mono); font-size:11px;
           letter-spacing:.1em; text-transform:uppercase; display:block; margin-bottom:4px; }
.ledger { font-family:var(--mono); font-size:13px; border:1px solid var(--line);
          border-radius:8px; background:var(--surface); margin:14px 0; }
.levent { display:flex; gap:14px; padding:8px 16px; border-bottom:1px solid var(--line); }
.levent:last-child { border-bottom:none; }
.levent .t { color:var(--muted); font-variant-numeric:tabular-nums; }
.levent .actor { color:var(--info); } .levent .actor.human { color:var(--good); }
footer { border-top:1px solid var(--line); padding:28px 0 60px; }
footer p { color:var(--muted); }
code { font-family:var(--mono); font-size:.92em; background:var(--surface2);
       padding:1px 5px; border-radius:4px; }
"""

html = f"""<meta charset="utf-8">
<title>Live Case: An Agent Fixes a Real GitHub Issue</title>
<div class="wrap">
<header>
  <div class="eyebrow">OpenAgentOS · live case · real repo, real issue, real PR</div>
  <h1>An autonomous agent just fixed a real GitHub issue. A human owns the merge.</h1>
  <p class="lede">Everything on this page happened against someone else's repository:
  the issue text as written, the repo's actual branch, its real test suite as the
  judge — ending in an upstream pull request. Run
  <code>{DATA['run_id']}</code>, replayed from the audit log.</p>
</header>

<section>
  <h2>The case: a security guard that vanishes under -O</h2>
  <p><a href="https://github.com/mgomezdev/themis/issues/38">mgomezdev/themis#38</a>:
  the backend's API-key auth guards <code>require_scope()</code> with an
  <code>assert</code> — the only scope-typo check across 113 call sites.</p>
  <div class="codebox"><span class="bad">assert scope in SCOPES, f"unknown scope {{scope!r}}"</span></div>
  <p class="mut">Python strips <code>assert</code> statements under <code>-O</code>.
  In optimized mode the check silently vanishes — a typo'd scope becomes a
  dependency that never validates anything. It looks like validation, passes every
  normal test run, and disappears exactly when optimization is on.</p>
</section>

<section>
  <h2>Proof before the agent: acceptance tests from the issue text</h2>
  <p>Before the agent saw anything, the acceptance criteria were written as tests —
  including a subprocess test that imports the real module under
  <code>python -O</code> and demands the guard still fire. On the untouched code:</p>
  <div class="chips">
    <span class="chip good">known scope accepted — PASS</span>
    <span class="chip bad">unknown scope raises ValueError — FAIL</span>
    <span class="chip bad">guard survives python -O — FAIL</span>
  </div>
  <p class="mut">2 of 3 failing. The bug is demonstrated mechanically, not narrated.</p>
</section>

<section>
  <h2>The run, live</h2>
  <div class="gifframe"><img
    src="data:image/gif;base64,{gif_b64}"
    alt="terminal recording of the SWE agent fixing themis issue 38 end to end"
    width="1100"></div>
  <p>One attempt. The agent picked <code>app/auth.py</code> from the real package
  tree, wrote the fix, and the repo's pytest went 3/3 green — including the
  <code>-O</code> subprocess proof
  (<code>{test_payload.get('output_tail', '').strip().splitlines()[-1] if test_payload.get('output_tail') else '5 passed'}</code>).</p>
  <div class="quote"><b>The LLM reviewer, unprompted</b>
  {review[:490]}…</div>
  <div class="ledger">{trail_rows}</div>
</section>

<section>
  <h2>The entire diff</h2>
  <div class="codebox"><span class="bad">-    assert scope in SCOPES, f"unknown scope {{scope!r}}"</span>
<span class="good">+    if scope not in SCOPES:</span>
<span class="good">+        raise ValueError(f"unknown scope {{scope!r}}")</span></div>
  <p class="mut">Small is the point. No refactoring sprawl, no "improvements" to
  adjacent code, no invented abstractions. Issue in, minimal reviewed patch out —
  exactly the fix the maintainer asked for.</p>
</section>

<section>
  <h2>Upstream, honestly</h2>
  <p>The fix — plus the three acceptance tests rewritten in the repo's own
  conventions, plus a before/after run of their full suite showing zero
  regressions — is now
  <a href="https://github.com/mgomezdev/themis/pull/48">pull request #48</a>,
  awaiting maintainer review. The PR states its provenance plainly: authored by an
  autonomous agent (plan → code → pytest gate → LLM review → human-approved
  merge), then reviewed and submitted by a human.</p>
  <div class="chips">
    <span class="chip acc">merge gate: human-owned</span>
    <span class="chip acc">merge: idempotent</span>
    <span class="chip acc">every step: audited</span>
  </div>
</section>

<footer>
  <p><strong style="color:var(--text)">What reality taught the agent:</strong>
  fixtures flatter you; real repos don't. Contact with this one repo forced two
  embarrassingly ordinary upgrades — recursive file discovery (the planner only
  saw the workspace root) and a bigger output budget for real-sized files. That's
  what "production-grade" actually is: mundane gaps, fixed mechanically, under
  test.</p>
  <p>The same runtime runs six domain agents — HR, Finance, IT Ops, Support, SRE,
  SWE — with zero forks of the core. Code and the full series:
  <a href="https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems">
  github.com/lonexreb/Production-Grade-Agentic-AI-Systems</a></p>
</footer>
</div>
<style>{css}</style>
"""

out = HERE / "live-case-blog.html"
out.write_text(html)
print(f"built {out} ({len(html)/1024:.0f} KB)")

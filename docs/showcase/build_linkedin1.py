#!/usr/bin/env python3
"""Assemble the LinkedIn post #1 artifact: three real failures, replayed live."""

import base64
from pathlib import Path

REPO = Path("/Users/shubh-trips/Documents/personal-project/production-autonomous-ai-agents")
HERE = Path(__file__).parent


def gif(name: str) -> str:
    data = base64.b64encode((REPO / "docs/media" / name).read_bytes()).decode()
    return f"data:image/gif;base64,{data}"


CASES = [
    {
        "n": "01",
        "title": "The side effect that ran twice",
        "report": ('Reported on the <a href="https://forum.langchain.com/t/twice-execution-of-agent-when-using-the-interrupt/2964">'
                   "LangChain forum</a> and dissected in "
                   '<a href="https://blog.raed.dev/posts/langgraph-hitl/">a widely shared write-up</a>: '
                   "LangGraph's <code>interrupt()</code> works by re-running the node it was called "
                   "from. Any side effect placed <em>before</em> the interrupt executes again when "
                   "the human answers — duplicate records, double writes."),
        "bug": ("2 rows", "one approved action, naive node"),
        "fix": ("1 row", "gate-first + idempotency ledger"),
        "primitive": ("interrupt() is the FIRST statement of the gated node, and the effect sits "
                      "behind an <code>execute_once</code> key — a re-run replays the stored "
                      "result instead of executing."),
        "gif": "p1-hitl-double-execution.gif",
        "alt": "terminal recording: naive interrupt writes 2 rows, fixed pattern writes 1",
    },
    {
        "n": "02",
        "title": "The retry that charged twice",
        "report": ('An r/AI_Agents developer\'s fulfillment agent double-triggered a Printify order '
                   'when the confirmation arrived during a retry window. The canonical variant is the '
                   '<a href="https://www.channel.tel/blog/idempotent-tool-calls-agent-retry-safety">'
                   "Stripe-timeout double-charge</a>: the charge <em>commits server-side</em>, the "
                   "response is lost, the retry pays again. Reliable test networks hide it; "
                   "production networks don't."),
        "bug": ("2 charges", "one order, naive retry"),
        "fix": ("1 charge", "deterministic key, provider dedupes"),
        "primitive": ("The runtime's side-effect key (<code>run_id:node:scope</code> — stable "
                      "across retries by construction) is forwarded to the provider as <em>its</em> "
                      "idempotency key. The retry still fires; the provider dedupes it."),
        "gif": "p2-retry-double-charge.gif",
        "alt": "terminal recording: naive retry charges twice, keyed retry charges once",
    },
    {
        "n": "03",
        "title": "Crashed at item 37, restarted at item 1",
        "report": ('The pattern across <a href="https://dev.to/george_belsky/your-ai-agent-crashed-at-step-47-now-what-41mb">'
                   "dev.to</a> and <a href=\"https://klementgunndu1.hashnode.dev/your-ai-agent-just-lost-3-hours-of-work-heres-why\">"
                   "engineering blogs</a>: an agent researching 50 companies makes it through 37, "
                   "the server restarts — and it starts over from company 1, re-spending real API "
                   "money on work it already did. State lived in process memory; the process died; "
                   "the state died with it."),
        "bug": ("$10.80 re-spent", "36 items redone from memory-only state"),
        "fix": ("$0.00 re-spent", "fresh process resumes at item 37"),
        "primitive": ("One item per graph superstep means one checkpoint per item — for free. "
                      "Nobody wrote checkpointing code; durability is a property of the runtime, "
                      "not a feature you remember to add."),
        "gif": "p3-crash-at-step-37.gif",
        "alt": "terminal recording: batch killed at item 37 resumes at 37 and finishes all 50",
    },
]

css = """
:root {
  --ground: #eef1f4; --surface: #ffffff; --surface2: #e4e9ee; --line: #ccd4dc;
  --text: #1a2229; --muted: #5c6a76; --accent: #b87a1e;
  --accent-soft: rgba(184,122,30,.12); --good: #2e7d5b; --bad: #b04a4a;
  --mono: ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --display: "Avenir Next",Avenir,Futura,"Century Gothic",system-ui,sans-serif;
  --body: system-ui,-apple-system,"Segoe UI",sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:#101418; --surface:#1a2027; --surface2:#232b34; --line:#2e3944;
    --text:#e8edf2; --muted:#8a96a3; --accent:#e8a33d;
    --accent-soft:rgba(232,163,61,.14); --good:#5fb88a; --bad:#d96a6a;
  }
}
:root[data-theme="dark"] {
  --ground:#101418; --surface:#1a2027; --surface2:#232b34; --line:#2e3944;
  --text:#e8edf2; --muted:#8a96a3; --accent:#e8a33d;
  --accent-soft:rgba(232,163,61,.14); --good:#5fb88a; --bad:#d96a6a;
}
* { box-sizing: border-box; }
body { margin:0; background:var(--ground); color:var(--text);
       font-family:var(--body); font-size:16px; line-height:1.6; }
a { color: var(--accent); }
.wrap { max-width: 860px; margin: 0 auto; padding: 0 22px; }
header { padding: 54px 0 34px; }
.eyebrow { font-family:var(--mono); font-size:12px; letter-spacing:.14em;
           text-transform:uppercase; color:var(--accent); }
h1 { font-family:var(--display); font-weight:700; letter-spacing:-.015em;
     font-size:clamp(30px,6vw,44px); line-height:1.1; margin:10px 0 14px;
     text-wrap:balance; }
.lede { color:var(--muted); max-width:60ch; }
.case { border-top:1px solid var(--line); padding:38px 0 44px; }
.casehead { display:flex; align-items:baseline; gap:14px; }
.casenum { font-family:var(--mono); font-size:13px; color:var(--accent); }
h2 { font-family:var(--display); font-size:26px; font-weight:700; margin:0;
     letter-spacing:-.01em; text-wrap:balance; }
.report { color:var(--muted); max-width:66ch; margin:12px 0 18px; }
.scoreboard { display:flex; gap:12px; flex-wrap:wrap; margin:0 0 18px; }
.score { flex:1; min-width:220px; border:1px solid var(--line); border-radius:8px;
         background:var(--surface); padding:14px 18px; }
.score .tag { font-family:var(--mono); font-size:11px; letter-spacing:.12em;
              text-transform:uppercase; display:block; margin-bottom:4px; }
.score.bug .tag { color:var(--bad); } .score.fixed .tag { color:var(--good); }
.score b { font-family:var(--mono); font-size:24px; font-variant-numeric:tabular-nums; }
.score.bug b { color:var(--bad); } .score.fixed b { color:var(--good); }
.score span.det { display:block; color:var(--muted); font-size:13px; }
.gifframe { border:1px solid var(--line); border-radius:10px; overflow:hidden;
            background:#1a1d29; margin:0 0 16px; }
.gifframe img { display:block; width:100%; height:auto; }
.primitive { padding:12px 16px; background:var(--accent-soft);
             border-left:3px solid var(--accent); border-radius:0 8px 8px 0;
             font-size:14.5px; max-width:70ch; }
.primitive b { color:var(--accent); font-family:var(--mono); font-size:11px;
               letter-spacing:.1em; text-transform:uppercase; display:block;
               margin-bottom:4px; }
footer { border-top:1px solid var(--line); padding:30px 0 60px; }
.statrow { display:flex; gap:12px; flex-wrap:wrap; margin:18px 0; }
.stat { background:var(--surface); border:1px solid var(--line); border-radius:8px;
        padding:10px 16px; }
.stat b { display:block; font-family:var(--mono); font-size:20px; color:var(--accent);
          font-variant-numeric:tabular-nums; }
.stat span { font-size:12px; color:var(--muted); }
footer p { color:var(--muted); max-width:66ch; }
code { font-family:var(--mono); font-size:.92em; background:var(--surface2);
       padding:1px 5px; border-radius:4px; }
"""

case_html = ""
for c in CASES:
    case_html += f"""
<section class="case">
  <div class="casehead"><span class="casenum">{c['n']}</span><h2>{c['title']}</h2></div>
  <p class="report">{c['report']}</p>
  <div class="scoreboard">
    <div class="score bug"><span class="tag">The bug, reproduced</span>
      <b>{c['bug'][0]}</b><span class="det">{c['bug'][1]}</span></div>
    <div class="score fixed"><span class="tag">The fix, proven</span>
      <b>{c['fix'][0]}</b><span class="det">{c['fix'][1]}</span></div>
  </div>
  <div class="gifframe"><img src="{gif(c['gif'])}" alt="{c['alt']}" loading="lazy"
       width="1050"></div>
  <div class="primitive"><b>The primitive</b>{c['primitive']}</div>
</section>"""

html = f"""<meta charset="utf-8">
<title>Three Real Agent Failures, Replayed</title>
<div class="wrap">
<header>
  <div class="eyebrow">OpenAgentOS · real reported failures · runnable proofs</div>
  <h1>Your AI agent charged a customer twice. It's not the model's fault.</h1>
  <p class="lede">Three failures real developers reported publicly — reproduced as
  runnable code first (the bug, with numbers), then fixed with boring runtime
  primitives (the proof, with numbers). The terminal recordings below are the
  actual scenarios running; both halves execute in CI on every push.</p>
</header>
{case_html}
<footer>
  <p><strong style="color:var(--text)">The common thread:</strong> none of these are
  model problems, and none of the fixes are clever. Idempotency ledgers, durable
  pauses, checkpoint-per-step — mechanical primitives, applied by a runtime so
  every agent gets them without remembering to.</p>
  <div class="statrow">
    <div class="stat"><b>3/3</b><span>bugs reproduced + fixed in CI</span></div>
    <div class="stat"><b>6</b><span>tagged releases</span></div>
    <div class="stat"><b>6</b><span>apps, one runtime</span></div>
    <div class="stat"><b>1</b><span>real upstream PR by the SWE agent</span></div>
  </div>
  <p>Code, tests, and write-ups:
  <a href="https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems">
  github.com/lonexreb/Production-Grade-Agentic-AI-Systems</a></p>
</footer>
</div>
<style>{css}</style>
"""

out = HERE / "three-failures-linkedin.html"
out.write_text(html)
print(f"built {out} ({len(html)/1024:.0f} KB)")

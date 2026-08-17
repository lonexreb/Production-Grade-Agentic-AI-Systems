/* OpenAgentOS showcase — step player over real recorded runs. DATA injected at build. */
"use strict";

const CASES = window.OAOS_CASES; // built server-side from Postgres exports

const stage = document.getElementById("stage");
const rail = document.getElementById("rail");
let activeCase = null;
let activeVariant = null;
let stepIdx = 0;
let playTimer = null;

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtPayload(obj) {
  if (obj == null) return "";
  const json = JSON.stringify(obj, null, 2);
  return esc(json).replace(/"([^"]+)":/g, '<span class="k">"$1":</span>');
}

function fmtDiff(patch) {
  return patch.split("\n").map(line => {
    const e = esc(line);
    if (line.startsWith("+++") || line.startsWith("---")) return `<span class="meta">${e}</span>`;
    if (line.startsWith("@@")) return `<span class="hunk">${e}</span>`;
    if (line.startsWith("+")) return `<span class="add">${e}</span>`;
    if (line.startsWith("-")) return `<span class="del">${e}</span>`;
    if (line.startsWith("commit") || line.startsWith("Author") || line.startsWith("Date")) return `<span class="meta">${e}</span>`;
    return e;
  }).join("\n");
}

function actorClass(actor) {
  if (actor.startsWith("policy:")) return "actor policy";
  if (actor === "agent") return "actor";
  return "actor human";
}

function renderCase(caseId, variantId) {
  const c = CASES.find(x => x.id === caseId);
  activeCase = c;
  activeVariant = c.variants.find(v => v.id === variantId) || c.variants[0];
  stepIdx = 0;
  stopPlay();

  document.querySelectorAll(".railbtn").forEach(b =>
    b.classList.toggle("active", b.dataset.case === caseId));

  const v = activeVariant;
  const variantBtns = c.variants.length > 1
    ? `<div class="variants" role="tablist">` + c.variants.map(x =>
        `<button class="varbtn ${x.id === v.id ? "active" : ""}" data-var="${x.id}">${esc(x.label)}</button>`
      ).join("") + `</div>`
    : "";

  const flow = `<div class="flow" aria-label="workflow graph">` +
    c.nodes.map((n, i) =>
      (i ? `<span class="arrow">&#8594;</span>` : "") +
      `<span class="node ${n.gate ? "gate" : ""}" data-node="${n.id}">${esc(n.label)}</span>`
    ).join("") + `</div>`;

  const ledgerRows = v.steps.filter(s => s.audit).map((s, i) =>
    `<div class="levent" data-step="${v.steps.indexOf(s)}">
      <span class="t">${esc(s.audit.t || "")}</span>
      <span class="${actorClass(s.audit.actor)}">${esc(s.audit.actor)}</span>
      <span class="ev ${/reject/.test(s.audit.event) ? "reject" : ""}">${esc(s.audit.event)}</span>
    </div>`).join("");

  stage.innerHTML = `
    <h2>${esc(c.title)}</h2>
    <p class="thesis">${c.thesis}</p>
    <p class="runidline">real recorded run: <b>${esc(v.run_id)}</b> &nbsp;·&nbsp; ${esc(c.phase)}</p>
    ${variantBtns}
    ${flow}
    <div class="player">
      <div class="panel">
        <h3>Step ${c.extra_panel ? "&amp; artifact" : ""}</h3>
        <div class="stepbody" id="stepbody"></div>
        <div class="controls">
          <button id="prev">&#8592; Prev</button>
          <button id="next">Next &#8594;</button>
          <button id="play" class="play">&#9654; Play</button>
          <span class="stepcount" id="stepcount"></span>
        </div>
      </div>
      <div class="panel">
        <h3>Audit ledger (append-only, from Postgres)</h3>
        <div class="ledger" id="ledger">${ledgerRows || '<div class="levent seen"><span class="ev">no audit events for this pattern &mdash; see inspector</span></div>'}</div>
        <h3>Event payload inspector</h3>
        <pre class="payload" id="payload"></pre>
      </div>
    </div>
    ${c.footer_html || ""}
  `;

  stage.querySelectorAll(".varbtn").forEach(b =>
    b.addEventListener("click", () => renderCase(caseId, b.dataset.var)));
  document.getElementById("prev").addEventListener("click", () => go(stepIdx - 1));
  document.getElementById("next").addEventListener("click", () => go(stepIdx + 1));
  document.getElementById("play").addEventListener("click", togglePlay);
  go(0);
}

function go(i) {
  const steps = activeVariant.steps;
  stepIdx = Math.max(0, Math.min(steps.length - 1, i));
  const s = steps[stepIdx];

  document.querySelectorAll(".node").forEach(n => {
    n.classList.remove("live");
    const passed = steps.slice(0, stepIdx + 1).some(st => st.node === n.dataset.node);
    n.classList.toggle("done", passed);
  });
  if (s.node) {
    const el = document.querySelector(`.node[data-node="${s.node}"]`);
    if (el) { el.classList.add("live"); el.classList.remove("done"); }
  }

  const body = document.getElementById("stepbody");
  body.innerHTML = `
    <p class="steptitle">${esc(s.title)}</p>
    <p class="stepnote">${s.note}</p>
    ${s.guarantee ? `<div class="guarantee"><b>${esc(s.guarantee[0])}</b>${s.guarantee[1]}</div>` : ""}
    ${s.html || ""}
  `;

  document.querySelectorAll(".levent").forEach(le => {
    const li = Number(le.dataset.step);
    le.classList.toggle("seen", li <= stepIdx);
    le.classList.toggle("current", li === stepIdx);
  });
  const cur = document.querySelector(".levent.current");
  if (cur) cur.scrollIntoView({ block: "nearest", behavior: "smooth" });

  document.getElementById("payload").innerHTML = s.audit
    ? fmtPayload(s.audit.payload)
    : '<span class="k">// no audit event at this step</span>';

  document.getElementById("stepcount").textContent = `${stepIdx + 1} / ${steps.length}`;
  document.getElementById("prev").disabled = stepIdx === 0;
  document.getElementById("next").disabled = stepIdx === steps.length - 1;
  if (stepIdx === steps.length - 1) stopPlay();
}

function togglePlay() {
  if (playTimer) { stopPlay(); return; }
  if (stepIdx === activeVariant.steps.length - 1) go(0);
  document.getElementById("play").innerHTML = "&#10073;&#10073; Pause";
  playTimer = setInterval(() => {
    if (stepIdx >= activeVariant.steps.length - 1) stopPlay();
    else go(stepIdx + 1);
  }, 2600);
}
function stopPlay() {
  clearInterval(playTimer);
  playTimer = null;
  const p = document.getElementById("play");
  if (p) p.innerHTML = "&#9654; Play";
}

/* rail */
CASES.forEach(c => {
  const b = document.createElement("button");
  b.className = "railbtn";
  b.dataset.case = c.id;
  b.innerHTML = `<span class="ph">${esc(c.phase_short)}</span><span>${esc(c.nav)}</span>`;
  b.addEventListener("click", () => renderCase(c.id));
  rail.appendChild(b);
});
renderCase(CASES[0].id);

/* expose formatters for build-time html in footer panels */
window.OAOS_fmtDiff = fmtDiff;
document.querySelectorAll("[data-diff-src]").forEach(el => {
  el.innerHTML = fmtDiff(el.textContent);
});

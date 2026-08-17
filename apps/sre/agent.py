"""SRE Agent: Kubernetes incident diagnosis + remediation on the runtime rails.

Built for ITBench-style scenarios (alerts + metrics + topology in; diagnosis +
remediation out) but generic over any cluster the kubeconfig reaches.

Flow: alerts -> evidence (topology, events, flags) -> diagnose (LLM, heavy) ->
remediate (constrained kubectl actions, policy-approved + audited, idempotent)
-> verify (alerts actually clear) -> report + episodic memory.

Safety model: the agent can only execute REMEDIATION_ACTIONS it proposed as
structured JSON — never raw shell. Reads are auto-tier; writes are approve-tier
behind an audited policy grant (benchmark mode) or a human gate.
"""

import json
import os
import subprocess
import time
from typing import Literal, TypedDict

import httpx
import psycopg

from langgraph.graph import END, START, StateGraph

from runtime import Tool, ToolRouter, audit, execute_once, llm, memory, side_effects
from runtime.config import DATABASE_URL
from runtime.tools import Approval

APP = "sre"
PROM = os.environ.get("OAOS_PROM_URL", "http://localhost:9090")
KCTX = os.environ.get("OAOS_KUBE_CONTEXT", "kind-kind-dev")

READ_VERBS = {"get", "describe", "logs", "top"}


def _kubectl(args: list[str], timeout: int = 30) -> str:
    proc = subprocess.run(["kubectl", "--context", KCTX, *args],
                          capture_output=True, text=True, timeout=timeout)
    return proc.stdout if proc.returncode == 0 else f"ERROR: {proc.stderr[:500]}"


def _k8s_read(args: list[str]) -> str:
    assert args and args[0] in READ_VERBS, f"read-only tool got verb {args[0]!r}"
    return _kubectl(args)[:8000]


def _get_alerts() -> list[dict]:
    resp = httpx.get(f"{PROM}/api/v1/alerts", timeout=15)
    resp.raise_for_status()
    return [
        {"name": a["labels"].get("alertname"), "state": a["state"],
         "labels": {k: v for k, v in a["labels"].items()
                    if k in ("namespace", "service", "deployment", "pod", "severity")}}
        for a in resp.json()["data"]["alerts"] if a["state"] == "firing"
    ]


def _apply_action(action: dict) -> dict:
    """Execute ONE structured remediation action. The only write path."""
    kind = action["action"]
    ns = action["namespace"]
    if kind == "patch_configmap":
        out = _kubectl(["-n", ns, "patch", "configmap", action["name"],
                        "--type", "merge", "-p", json.dumps(action["patch"])])
    elif kind == "rollout_restart":
        target = action.get("name", "deployment")
        out = _kubectl(["-n", ns, "rollout", "restart",
                        *( ["deployment", target] if target != "deployment"
                           else ["deployment"] )])
    elif kind == "scale":
        out = _kubectl(["-n", ns, "scale", f"deployment/{action['name']}",
                        f"--replicas={action['replicas']}"])
    elif kind == "delete_pod":
        out = _kubectl(["-n", ns, "delete", "pod", action["name"]])
    else:
        raise ValueError(f"unknown remediation action: {kind}")
    return {"action": kind, "result": out[:300]}


router = ToolRouter()
router.register(Tool(name="k8s_read", fn=_k8s_read, timeout_s=45))
router.register(Tool(name="get_alerts", fn=_get_alerts, timeout_s=30, max_retries=3))
router.register(Tool(name="remediate", fn=_apply_action, timeout_s=60,
                     risk_tier="approve"))


class SREState(TypedDict, total=False):
    alerts: list
    evidence: str
    diagnosis: dict          # {root_cause, entities, actions[]}
    approval: dict
    applied: list
    verified: bool
    response: str


def make_alerts_node(run_id: str):
    def alerts_node(state: SREState) -> SREState:
        alerts = router.call("get_alerts", run_id=run_id)
        with psycopg.connect(DATABASE_URL) as conn:
            audit.ensure_schema(conn)
            audit.append(conn, run_id, "agent", "alerts_observed",
                         {"count": len(alerts), "alerts": alerts[:10]})
        return {"alerts": alerts}

    return alerts_node


def make_evidence_node(run_id: str):
    def evidence_node(state: SREState) -> SREState:
        namespaces = sorted({a["labels"].get("namespace") for a in state["alerts"]
                             if a["labels"].get("namespace")}) or ["otel-demo"]
        chunks = []
        for ns in namespaces[:3]:
            chunks.append(f"## namespace {ns}\n"
                          f"### deployments\n"
                          + router.call("k8s_read", run_id=run_id,
                                        args=["get", "deploy", "-n", ns, "-o", "wide"])
                          + "\n### recent warning events\n"
                          + router.call("k8s_read", run_id=run_id,
                                        args=["get", "events", "-n", ns,
                                              "--field-selector", "type=Warning",
                                              "--sort-by", ".lastTimestamp"])[-3000:]
                          + "\n### configmaps\n"
                          + router.call("k8s_read", run_id=run_id,
                                        args=["get", "configmap", "-n", ns]))
        # feature-flag configs are a common OTel-demo fault vector — pull contents
        for ns in namespaces[:3]:
            flag_cm = router.call("k8s_read", run_id=run_id,
                                  args=["get", "configmap", "-n", ns,
                                        "flagd-config", "-o", "jsonpath={.data}"])
            if not flag_cm.startswith("ERROR"):
                chunks.append(f"## flagd-config ({ns})\n{flag_cm[:4000]}")
        evidence = "\n".join(chunks)[:24000]
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, "agent", "evidence_gathered",
                         {"namespaces": namespaces, "chars": len(evidence)})
        return {"evidence": evidence}

    return evidence_node


DIAGNOSE_PROMPT = """You are an SRE diagnosing a Kubernetes incident.

FIRING ALERTS:
{alerts}

EVIDENCE:
{evidence}

Past incidents that looked similar (episodic memory):
{episodes}

Identify the root cause and a minimal remediation. Reply with ONLY JSON:
{{"root_cause": "<one sentence>",
  "entities": ["<contributing-factor entities: deployment/configmap/pod names>"],
  "actions": [
    {{"action": "patch_configmap", "namespace": "...", "name": "...",
      "patch": {{"data": {{"<key>": "<full new value>"}}}}}},
    {{"action": "rollout_restart", "namespace": "...", "name": "deployment"}}
  ]}}
Allowed actions: patch_configmap, rollout_restart, scale, delete_pod.
Prefer the smallest change that removes the fault (e.g. disable a bad feature
flag) over broad restarts. Only include restarts if config consumers need them.
"""


def make_diagnose_node(run_id: str):
    def diagnose_node(state: SREState) -> SREState:
        with psycopg.connect(DATABASE_URL) as conn:
            memory.ensure_schema(conn)
            alert_names = " ".join(a["name"] or "" for a in state["alerts"])
            episodes = memory.recall(conn, APP, f"incident {alert_names}")
        raw = llm.complete(
            DIAGNOSE_PROMPT.format(
                alerts=json.dumps(state["alerts"], indent=1)[:4000],
                evidence=state["evidence"],
                episodes=json.dumps(episodes)[:2000] or "none",
            ),
            system="Reply with only the JSON object, no fences.",
            max_tokens=1500,
        )
        text = raw.strip().strip("`")
        text = text[text.index("{"):text.rindex("}") + 1]
        diagnosis = json.loads(text)
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, "agent", "diagnosis_made", diagnosis)
        return {"diagnosis": diagnosis}

    return diagnose_node


def make_gate_node(run_id: str):
    def gate_node(state: SREState) -> SREState:
        # ponytail: benchmark mode uses an audited policy grant; swap for
        # interrupt() (as in every other app) when a human is on call.
        decision = {"approved": True, "by": "policy:sre-benchmark-mode",
                    "actions": len(state["diagnosis"].get("actions", []))}
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, decision["by"], "approval_granted", decision)
        return {"approval": decision}

    return gate_node


def make_remediate_node(run_id: str):
    def remediate_node(state: SREState) -> SREState:
        applied = []
        with psycopg.connect(DATABASE_URL) as conn:
            side_effects.ensure_schema(conn)
            for i, action in enumerate(state["diagnosis"].get("actions", [])[:5]):
                result = execute_once(
                    conn, side_effects.make_key(run_id, "remediate", scope=str(i)),
                    run_id,
                    lambda a=action: router.call(
                        "remediate", run_id=run_id,
                        approval=Approval(approved=True, by=state["approval"]["by"]),
                        action=a),
                )
                applied.append(result)
                audit.append(conn, run_id, "agent", "tool_call",
                             {"tool": "remediate", "result": result})
        return {"applied": applied}

    return remediate_node


def make_verify_node(run_id: str, wait_s: int = 180):
    def verify_node(state: SREState) -> SREState:
        deadline = time.time() + wait_s
        remaining = state["alerts"]
        while time.time() < deadline:
            remaining = router.call("get_alerts", run_id=run_id)
            if not remaining:
                break
            time.sleep(15)
        verified = not remaining
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, "agent", "verification",
                         {"alerts_cleared": verified,
                          "remaining": [a["name"] for a in remaining][:5]})
        return {"verified": verified}

    return verify_node


def make_report_node(run_id: str):
    def report_node(state: SREState) -> SREState:
        d = state["diagnosis"]
        outcome = "resolved" if state["verified"] else "not-resolved (escalate)"
        with psycopg.connect(DATABASE_URL) as conn:
            memory.write_episode(
                conn, APP, run_id,
                f"incident {' '.join(a['name'] or '' for a in state['alerts'])[:100]}"
                f" root-cause {d.get('root_cause', '')[:120]} {outcome}",
                {"ok": state["verified"], "entities": d.get("entities", [])},
            )
            audit.append(conn, run_id, "agent", "incident_closed",
                         {"outcome": outcome})
        return {"response": f"{outcome}: {d.get('root_cause', 'unknown')} "
                            f"(entities: {', '.join(d.get('entities', [])[:4])})"}

    return report_node


def route_after_alerts(state: SREState) -> Literal["evidence", "report_quiet"]:
    return "evidence" if state["alerts"] else "report_quiet"


def build_graph(run_id: str) -> StateGraph:
    g = StateGraph(SREState)
    g.add_node("alerts", make_alerts_node(run_id))
    g.add_node("evidence", make_evidence_node(run_id))
    g.add_node("diagnose", make_diagnose_node(run_id))
    g.add_node("gate", make_gate_node(run_id))
    g.add_node("remediate", make_remediate_node(run_id))
    g.add_node("verify", make_verify_node(run_id))
    g.add_node("report", make_report_node(run_id))
    g.add_node("report_quiet",
               lambda s: {"response": "no firing alerts — nothing to do",
                          "verified": True, "diagnosis": {}})
    g.add_edge(START, "alerts")
    g.add_conditional_edges("alerts", route_after_alerts)
    g.add_edge("evidence", "diagnose")
    g.add_edge("diagnose", "gate")
    g.add_edge("gate", "remediate")
    g.add_edge("remediate", "verify")
    g.add_edge("verify", "report")
    g.add_edge("report", END)
    g.add_edge("report_quiet", END)
    return g

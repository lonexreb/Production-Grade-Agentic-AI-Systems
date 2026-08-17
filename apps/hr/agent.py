"""HR Agent: employee email -> intent -> policy -> payroll change (human-approved) -> notify.

The payroll tool is approve-tier: the router refuses it without a granting
Approval, and the graph obtains one by pausing at interrupt(). The paused run is
fully checkpointed — it survives restarts and resumes from any process via
Runtime.resume(decision=...). Every consequential event lands in the audit log.

Node layout note: interrupt() is the FIRST statement of the gated node, so the
node's re-execution on resume replays nothing else; the payroll side effect
itself is additionally guarded by an idempotency key.

Run: python -m apps.hr.demo
"""

from typing import TypedDict

import psycopg

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from runtime import Tool, ToolRouter, audit, execute_once, llm, side_effects
from runtime.config import DATABASE_URL
from runtime.tools import Approval

POLICIES = {
    "update_direct_deposit": "Direct deposit changes require manager approval "
                             "and take effect next pay cycle.",
    "pto_balance": "PTO balances are self-service; no approval needed.",
}


class HRState(TypedDict, total=False):
    email: str
    employee: str
    intent: str
    policy: str
    approval: dict
    payroll_result: dict
    response: str


def _update_payroll(employee: str, detail: str) -> dict:
    """Stands in for the payroll API. Approve-tier: never runs without a human."""
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS payroll_changes"
            " (id serial PRIMARY KEY, employee text, detail text)"
        )
        conn.execute(
            "INSERT INTO payroll_changes (employee, detail) VALUES (%s, %s)",
            (employee, detail),
        )
        conn.commit()
    return {"changed": detail, "employee": employee}


def _notify(employee: str, message: str) -> dict:
    return {"notified": employee, "message": message}  # stands in for email/Slack


router = ToolRouter()
router.register(Tool(name="update_payroll", fn=_update_payroll, risk_tier="approve"))
router.register(Tool(name="notify", fn=_notify, risk_tier="notify"))


def intent_node(state: HRState) -> HRState:
    """LLM classifier when a key is configured; keyword fallback otherwise
    so tests and CI never need secrets."""
    label = llm.complete(
        "Classify this HR email as exactly one of: "
        f"{', '.join(POLICIES)}. Reply with the label only.\n\n{state['email']}",
        max_tokens=10, tier="light",
    )
    if label and label.strip() in POLICIES:
        return {"intent": label.strip()}
    text = state["email"].lower()
    intent = "update_direct_deposit" if "direct deposit" in text or "bank" in text \
        else "pto_balance"
    return {"intent": intent}


def policy_node(state: HRState) -> HRState:
    return {"policy": POLICIES[state["intent"]]}


def make_request_approval_node(run_id: str):
    def request_approval(state: HRState) -> HRState:
        with psycopg.connect(DATABASE_URL) as conn:
            audit.ensure_schema(conn)
            audit.append(conn, run_id, "agent", "approval_requested", {
                "intent": state["intent"], "employee": state["employee"],
                "policy": state["policy"],
            })
        return {}

    return request_approval


def make_payroll_node(run_id: str):
    def payroll_node(state: HRState) -> HRState:
        decision = interrupt({
            "question": f"Approve {state['intent']} for {state['employee']}?",
            "policy": state["policy"],
        })
        with psycopg.connect(DATABASE_URL) as conn:
            audit.ensure_schema(conn)
            if not decision.get("approved"):
                audit.append(conn, run_id, decision.get("by", "unknown"),
                             "approval_rejected", decision)
                return {"approval": decision}
            audit.append(conn, run_id, decision.get("by", "unknown"),
                         "approval_granted", decision)
            side_effects.ensure_schema(conn)
            result = execute_once(
                conn, side_effects.make_key(run_id, "payroll"), run_id,
                lambda: router.call(
                    "update_payroll", run_id=run_id,
                    approval=Approval(approved=True, by=decision.get("by", "unknown")),
                    employee=state["employee"], detail=state["intent"],
                ),
            )
            audit.append(conn, run_id, "agent", "tool_call",
                         {"tool": "update_payroll", "result": result})
        return {"approval": decision, "payroll_result": result}

    return payroll_node


def make_notify_node(run_id: str):
    def notify_node(state: HRState) -> HRState:
        approved = state["approval"].get("approved", False)
        message = (
            f"Your {state['intent']} request was completed."
            if approved else
            f"Your {state['intent']} request was declined: "
            f"{state['approval'].get('note', 'no reason given')}"
        )
        result = router.call("notify", run_id=run_id,
                             employee=state["employee"], message=message)
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, "agent", "notification_sent", result)
        return {"response": message}

    return notify_node


def build_graph(run_id: str) -> StateGraph:
    g = StateGraph(HRState)
    g.add_node("intent", intent_node)
    g.add_node("policy", policy_node)
    g.add_node("request_approval", make_request_approval_node(run_id))
    g.add_node("payroll", make_payroll_node(run_id))
    g.add_node("notify", make_notify_node(run_id))
    g.add_edge(START, "intent")
    g.add_edge("intent", "policy")
    g.add_edge("policy", "request_approval")
    g.add_edge("request_approval", "payroll")
    g.add_edge("payroll", "notify")
    g.add_edge("notify", END)
    return g

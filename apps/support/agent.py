"""Customer Support Agent: email -> intent -> KB answer | refund -> reply.

Refund policy is risk-routed like Finance, with an episodic-memory twist:
small refunds clear on audited policy approval UNLESS the customer already has
refund history (recall from episodic memory) — repeat refunders see a human,
whatever the amount.

The graph builder takes the refund limit as a parameter: `build_graph(run_id,
refund_limit=100)` is a CANDIDATE policy, which is what shadow mode evaluates
against recorded traffic before anyone flips the default.
"""

from typing import Literal, TypedDict

import psycopg

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from runtime import Tool, ToolRouter, audit, execute_once, memory, side_effects
from runtime.config import DATABASE_URL
from runtime.tools import Approval

APP = "support"
DEFAULT_REFUND_LIMIT = 50.0


class SupportState(TypedDict, total=False):
    email: str
    customer: str
    intent: str            # 'refund_request' | 'question'
    refund_amount: float
    repeat_refunder: bool
    kb_answer: str
    approval: dict
    refund_result: dict
    response: str


def _issue_refund(customer: str, amount: float) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS refunds"
            " (id serial PRIMARY KEY, customer text, amount numeric)"
        )
        conn.execute(
            "INSERT INTO refunds (customer, amount) VALUES (%s, %s)", (customer, amount)
        )
        conn.commit()
    return {"refunded": amount, "customer": customer}


def _send_reply(customer: str, message: str) -> dict:
    return {"to": customer, "message": message}  # stands in for the email API


router = ToolRouter()
router.register(Tool(name="issue_refund", fn=_issue_refund, risk_tier="approve"))
router.register(Tool(name="send_reply", fn=_send_reply, risk_tier="notify"))


def intent_node(state: SupportState) -> SupportState:
    # ponytail: keyword intent + amount parse; LLM classifier slots in exactly
    # like the HR agent's when real email variety demands it.
    text = state["email"].lower()
    if "refund" in text:
        amount = next((float(w.strip("$")) for w in text.split()
                       if w.startswith("$")), 0.0)
        return {"intent": "refund_request", "refund_amount": amount}
    return {"intent": "question"}


def history_node(state: SupportState) -> SupportState:
    with psycopg.connect(DATABASE_URL) as conn:
        memory.ensure_schema(conn)
        episodes = memory.recall(conn, APP, f"refund {state['customer']}")
    return {"repeat_refunder": len(episodes) > 0}


def make_kb_node(run_id: str):
    def kb_node(state: SupportState) -> SupportState:
        with psycopg.connect(DATABASE_URL) as conn:
            memory.ensure_schema(conn)
            facts = memory.facts_for(conn, APP, "kb:shipping")
        answer = facts[0]["fact"] if facts else "A human will follow up shortly."
        with psycopg.connect(DATABASE_URL) as conn:
            audit.ensure_schema(conn)
            audit.append(conn, run_id, "agent", "kb_answered", {"answer": answer})
        return {"kb_answer": answer, "approval": {"approved": False}}

    return kb_node


def route_intent(state: SupportState) -> Literal["kb", "refund_gate"]:
    return "refund_gate" if state["intent"] == "refund_request" else "kb"


def make_refund_gate_node(run_id: str, refund_limit: float):
    def refund_gate(state: SupportState) -> SupportState:
        small = state["refund_amount"] < refund_limit
        if small and not state["repeat_refunder"]:
            decision = {"approved": True, "by": f"policy:refund-under-{refund_limit:g}"}
        else:
            decision = interrupt({
                "question": f"Approve ${state['refund_amount']:,.2f} refund for "
                            f"{state['customer']}?",
                "repeat_refunder": state["repeat_refunder"],
            })
        with psycopg.connect(DATABASE_URL) as conn:
            audit.ensure_schema(conn)
            event = "approval_granted" if decision.get("approved") else "approval_rejected"
            audit.append(conn, run_id, decision.get("by", "unknown"), event, decision)
        return {"approval": decision}

    return refund_gate


def route_after_gate(state: SupportState) -> Literal["refund", "reply"]:
    return "refund" if state["approval"].get("approved") else "reply"


def make_refund_node(run_id: str):
    def refund_node(state: SupportState) -> SupportState:
        with psycopg.connect(DATABASE_URL) as conn:
            side_effects.ensure_schema(conn)
            result = execute_once(
                conn, side_effects.make_key(run_id, "refund"), run_id,
                lambda: router.call(
                    "issue_refund", run_id=run_id,
                    approval=Approval(approved=True, by=state["approval"]["by"]),
                    customer=state["customer"], amount=state["refund_amount"],
                ),
            )
            audit.append(conn, run_id, "agent", "tool_call",
                         {"tool": "issue_refund", "result": result})
        return {"refund_result": result}

    return refund_node


def make_reply_node(run_id: str):
    def reply_node(state: SupportState) -> SupportState:
        if state["intent"] == "question":
            message = state["kb_answer"]
        elif state["approval"].get("approved"):
            message = (f"Your ${state['refund_amount']:,.2f} refund is on the way"
                       f" (approved by {state['approval']['by']}).")
        else:
            message = "Your refund request was declined after review."
        router.call("send_reply", run_id=run_id,
                    customer=state["customer"], message=message)
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, "agent", "reply_sent", {"message": message})
            if state["intent"] == "refund_request":
                memory.write_episode(
                    conn, APP, run_id,
                    f"refund {state['customer']} ${state.get('refund_amount', 0)}"
                    f" {'granted' if state['approval'].get('approved') else 'declined'}",
                    {"ok": True},
                )
        return {"response": message}

    return reply_node


def build_graph(run_id: str, refund_limit: float = DEFAULT_REFUND_LIMIT) -> StateGraph:
    g = StateGraph(SupportState)
    g.add_node("intent", intent_node)
    g.add_node("history", history_node)
    g.add_node("kb", make_kb_node(run_id))
    g.add_node("refund_gate", make_refund_gate_node(run_id, refund_limit))
    g.add_node("refund", make_refund_node(run_id))
    g.add_node("reply", make_reply_node(run_id))
    g.add_edge(START, "intent")
    g.add_edge("intent", "history")
    g.add_conditional_edges("history", route_intent)
    g.add_conditional_edges("refund_gate", route_after_gate)
    g.add_edge("kb", "reply")
    g.add_edge("refund", "reply")
    g.add_edge("reply", END)
    return g

"""Finance Agent: invoice -> parse -> vendor check -> fraud check -> pay -> record.

Reuses the runtime unchanged: engine, router (approve-tier payment), idempotent
side effects, interrupt() approval, audit — plus MEMORY (module 4), which
changes behavior measurably:

  - semantic memory: an approved vendor becomes a durable fact; repeat invoices
    under the threshold clear on POLICY approval — zero human touches (audited).
  - episodic memory: past fraud episodes for a vendor force the human gate.

First invoice from a vendor pauses for a human. The second one doesn't.
That delta is the Phase 3 memory benchmark.
"""

from typing import Literal, TypedDict

import psycopg

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from runtime import Tool, ToolRouter, audit, execute_once, memory, side_effects
from runtime.config import DATABASE_URL
from runtime.tools import Approval

APP = "finance"
AUTO_APPROVE_LIMIT = 10_000  # invoices at/over this always see a human


class FinState(TypedDict, total=False):
    invoice: dict          # {vendor, amount, memo}
    vendor_verified: bool
    fraud_flag: bool
    approval: dict
    payment_result: dict
    response: str


def _pay_invoice(vendor: str, amount: float, memo: str) -> dict:
    """Stands in for the payment API. Approve-tier."""
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS payments"
            " (id serial PRIMARY KEY, vendor text, amount numeric, memo text)"
        )
        conn.execute(
            "INSERT INTO payments (vendor, amount, memo) VALUES (%s, %s, %s)",
            (vendor, amount, memo),
        )
        conn.commit()
    return {"paid": vendor, "amount": amount}


router = ToolRouter()
router.register(Tool(name="pay_invoice", fn=_pay_invoice, risk_tier="approve"))


def parse_node(state: FinState) -> FinState:
    # ponytail: invoices arrive pre-structured; OCR (e.g. an MCP document tool)
    # slots in here when real PDFs show up — control flow unchanged.
    inv = state["invoice"]
    assert inv["vendor"] and inv["amount"] > 0, "invalid invoice"
    return {}


def verify_vendor_node(state: FinState) -> FinState:
    with psycopg.connect(DATABASE_URL) as conn:
        memory.ensure_schema(conn)
        facts = memory.facts_for(conn, APP, f"vendor:{state['invoice']['vendor']}")
    verified = any(f["fact"] == "verified" for f in facts)
    return {"vendor_verified": verified}


def fraud_check_node(state: FinState) -> FinState:
    with psycopg.connect(DATABASE_URL) as conn:
        episodes = memory.recall(conn, APP, f"fraud {state['invoice']['vendor']}")
    return {"fraud_flag": any(not e["outcome"].get("ok", True) for e in episodes)}


def route_after_fraud(state: FinState) -> Literal["human_gate", "policy_approve"]:
    needs_human = (
        not state["vendor_verified"]
        or state["fraud_flag"]
        or state["invoice"]["amount"] >= AUTO_APPROVE_LIMIT
    )
    return "human_gate" if needs_human else "policy_approve"


def make_human_gate_node(run_id: str):
    def human_gate(state: FinState) -> FinState:
        decision = interrupt({
            "question": f"Approve payment of ${state['invoice']['amount']:,.2f} "
                        f"to {state['invoice']['vendor']}?",
            "vendor_verified": state["vendor_verified"],
            "fraud_flag": state["fraud_flag"],
        })
        with psycopg.connect(DATABASE_URL) as conn:
            audit.ensure_schema(conn)
            event = "approval_granted" if decision.get("approved") else "approval_rejected"
            audit.append(conn, run_id, decision.get("by", "unknown"), event, decision)
        return {"approval": decision}

    return human_gate


def make_policy_approve_node(run_id: str):
    def policy_approve(state: FinState) -> FinState:
        decision = {"approved": True, "by": "policy:verified-vendor-under-limit"}
        with psycopg.connect(DATABASE_URL) as conn:
            audit.ensure_schema(conn)
            audit.append(conn, run_id, decision["by"], "approval_granted", {
                **decision, "vendor": state["invoice"]["vendor"],
                "amount": state["invoice"]["amount"],
            })
        return {"approval": decision}

    return policy_approve


def route_after_approval(state: FinState) -> Literal["pay", "record"]:
    return "pay" if state["approval"].get("approved") else "record"


def make_pay_node(run_id: str):
    def pay_node(state: FinState) -> FinState:
        inv = state["invoice"]
        with psycopg.connect(DATABASE_URL) as conn:
            side_effects.ensure_schema(conn)
            result = execute_once(
                conn, side_effects.make_key(run_id, "pay"), run_id,
                lambda: router.call(
                    "pay_invoice", run_id=run_id,
                    approval=Approval(approved=True, by=state["approval"]["by"]),
                    vendor=inv["vendor"], amount=inv["amount"], memo=inv.get("memo", ""),
                ),
            )
            audit.append(conn, run_id, "agent", "tool_call",
                         {"tool": "pay_invoice", "result": result})
        return {"payment_result": result}

    return pay_node


def make_record_node(run_id: str):
    def record_node(state: FinState) -> FinState:
        inv, approved = state["invoice"], state["approval"].get("approved", False)
        by = state["approval"].get("by", "")
        human_approved_new_vendor = (
            approved and not state["vendor_verified"] and not by.startswith("policy:")
        )
        with psycopg.connect(DATABASE_URL) as conn:
            memory.ensure_schema(conn)
            if human_approved_new_vendor:
                memory.remember_fact(conn, APP, f"vendor:{inv['vendor']}", "verified",
                                     {"first_approved_by": by})
            memory.write_episode(
                conn, APP, run_id,
                f"invoice {inv['vendor']} ${inv['amount']}"
                f" {'paid' if approved else 'rejected'}",
                {"ok": approved, "by": by},
            )
        if approved:
            return {"response": f"invoice from {inv['vendor']} paid (approved by {by})"}
        return {"response": f"invoice from {inv['vendor']} rejected"}

    return record_node


def build_graph(run_id: str) -> StateGraph:
    g = StateGraph(FinState)
    g.add_node("parse", parse_node)
    g.add_node("verify_vendor", verify_vendor_node)
    g.add_node("fraud_check", fraud_check_node)
    g.add_node("human_gate", make_human_gate_node(run_id))
    g.add_node("policy_approve", make_policy_approve_node(run_id))
    g.add_node("pay", make_pay_node(run_id))
    g.add_node("record", make_record_node(run_id))
    g.add_edge(START, "parse")
    g.add_edge("parse", "verify_vendor")
    g.add_edge("verify_vendor", "fraud_check")
    g.add_conditional_edges("fraud_check", route_after_fraud)
    g.add_conditional_edges("human_gate", route_after_approval)
    g.add_conditional_edges("policy_approve", route_after_approval)
    g.add_edge("pay", "record")
    g.add_edge("record", END)
    return g

"""IT Ops Agent: ticket -> runbook -> auto-fix (with fallback) -> verify -> rollback/escalate.

Exercises the full failure-recovery ladder as first-class runtime features:
  retry     -> router (existing)
  fallback  -> Tool.fallback: restart_vpn falls back to reset_profile when the
               device is unreachable
  rollback  -> compensate_run: a fix that failed verification is UNDONE (saga),
               the side_effects row flips to 'compensated'
  escalate  -> interrupt(): a human decides what happens after auto-fix fails
  resume    -> engine (existing)

The runbook comes from procedural memory (versioned prompt_store) and the
version used is audited. Incident outcomes land in episodic memory.

Simulated fleet: device_state rows carry reachable/fixable_by — the infra
decides what works; the agent discovers it the hard way, like real life.
"""

from typing import Literal, TypedDict

import psycopg

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from runtime import Tool, ToolRouter, audit, execute_once, memory, side_effects
from runtime.config import DATABASE_URL

APP = "itops"

FLEET_DDL = """
CREATE TABLE IF NOT EXISTS device_state (
    device      text PRIMARY KEY,
    vpn_profile text NOT NULL DEFAULT 'corp-v1',
    healthy     bool NOT NULL DEFAULT false,
    reachable   bool NOT NULL DEFAULT true,
    fixable_by  text NOT NULL DEFAULT 'restart'   -- 'restart' | 'reset' | 'none'
);
CREATE TABLE IF NOT EXISTS itops_tickets (
    ticket_id  text PRIMARY KEY,
    device     text NOT NULL,
    status     text NOT NULL DEFAULT 'open'       -- open | resolved | escalated
);
"""


def ensure_fleet(conn: psycopg.Connection) -> None:
    conn.execute(FLEET_DDL)
    conn.commit()


class OpsState(TypedDict, total=False):
    ticket_id: str
    device: str
    runbook: str
    fix_result: dict
    fix_verified: bool
    rolled_back: bool
    approval: dict
    response: str


def _restart_vpn(device: str) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT reachable, fixable_by FROM device_state WHERE device = %s", (device,)
        ).fetchone()
        if row is None or not row[0]:
            raise ConnectionError(f"{device} unreachable")
        conn.execute(
            "UPDATE device_state SET healthy = (fixable_by = 'restart')"
            " WHERE device = %s", (device,),
        )
        conn.commit()
    return {"action": "restart_vpn", "device": device}


def _reset_profile(device: str) -> dict:
    """Out-of-band profile reset — works on unreachable devices, changes config."""
    with psycopg.connect(DATABASE_URL) as conn:
        prior = conn.execute(
            "SELECT vpn_profile FROM device_state WHERE device = %s", (device,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE device_state SET vpn_profile = 'default-v2',"
            " healthy = (fixable_by = 'reset') WHERE device = %s", (device,),
        )
        conn.commit()
    return {"action": "reset_profile", "device": device, "prior_profile": prior}


def undo_fix(result: dict) -> None:
    """Compensation handler for the fix node — dispatches on what actually ran."""
    if result.get("action") == "reset_profile":
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "UPDATE device_state SET vpn_profile = %s WHERE device = %s",
                (result["prior_profile"], result["device"]),
            )
            conn.commit()
    # restart_vpn changed no config -> nothing to undo


router = ToolRouter()
router.register(Tool(name="restart_vpn", fn=_restart_vpn, max_retries=0,
                     fallback="reset_profile"))
router.register(Tool(name="reset_profile", fn=_reset_profile, max_retries=0))


def make_runbook_node(run_id: str):
    def runbook_node(state: OpsState) -> OpsState:
        with psycopg.connect(DATABASE_URL) as conn:
            memory.ensure_schema(conn)
            runbook = memory.current_prompt(conn, APP, "runbook:vpn") or \
                "1. restart vpn service  2. reset network profile  3. escalate"
            audit.ensure_schema(conn)
            audit.append(conn, run_id, "agent", "runbook_selected",
                         {"runbook": runbook, "device": state["device"]})
        return {"runbook": runbook}

    return runbook_node


def make_fix_node(run_id: str):
    def fix_node(state: OpsState) -> OpsState:
        with psycopg.connect(DATABASE_URL) as conn:
            side_effects.ensure_schema(conn)
            result = execute_once(
                conn, side_effects.make_key(run_id, "fix"), run_id,
                lambda: router.call("restart_vpn", run_id=run_id,
                                    device=state["device"]),
            )
            audit.append(conn, run_id, "agent", "tool_call",
                         {"tool": result["action"], "result": result})
        return {"fix_result": result}

    return fix_node


def verify_node(state: OpsState) -> OpsState:
    with psycopg.connect(DATABASE_URL) as conn:
        healthy = conn.execute(
            "SELECT healthy FROM device_state WHERE device = %s", (state["device"],)
        ).fetchone()[0]
    return {"fix_verified": healthy}


def route_after_verify(state: OpsState) -> Literal["resolve", "rollback"]:
    return "resolve" if state["fix_verified"] else "rollback"


def make_rollback_node(run_id: str):
    def rollback_node(state: OpsState) -> OpsState:
        with psycopg.connect(DATABASE_URL) as conn:
            compensated = side_effects.compensate_run(conn, run_id, {"fix": undo_fix})
            audit.append(conn, run_id, "agent", "rollback",
                         {"compensated": compensated,
                          "fix": state["fix_result"]["action"]})
        return {"rolled_back": True}

    return rollback_node


def make_escalate_node(run_id: str):
    def escalate_node(state: OpsState) -> OpsState:
        decision = interrupt({
            "question": f"Auto-fix failed for {state['device']} (tried "
                        f"{state['fix_result']['action']}, rolled back). "
                        "Assign to on-site tech?",
            "runbook": state["runbook"],
        })
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, decision.get("by", "unknown"),
                         "escalation_decided", decision)
        return {"approval": decision}

    return escalate_node


def make_resolve_node(run_id: str):
    def resolve_node(state: OpsState) -> OpsState:
        escalated = state.get("rolled_back", False)
        status = "escalated" if escalated else "resolved"
        with psycopg.connect(DATABASE_URL) as conn:
            ensure_fleet(conn)
            conn.execute(
                "UPDATE itops_tickets SET status = %s WHERE ticket_id = %s",
                (status, state["ticket_id"]),
            )
            conn.commit()
            memory.write_episode(
                conn, APP, run_id,
                f"ticket {state['device']} vpn {status}"
                f" via {state.get('fix_result', {}).get('action', 'none')}",
                {"ok": not escalated, "status": status},
            )
            audit.append(conn, run_id, "agent", "ticket_updated",
                         {"ticket": state["ticket_id"], "status": status})
        if escalated:
            return {"response": f"ticket {state['ticket_id']} escalated to "
                                f"{state['approval'].get('assign_to', 'on-site tech')}"}
        return {"response": f"ticket {state['ticket_id']} resolved automatically"
                            f" ({state['fix_result']['action']})"}

    return resolve_node


def build_graph(run_id: str) -> StateGraph:
    g = StateGraph(OpsState)
    g.add_node("runbook", make_runbook_node(run_id))
    g.add_node("fix", make_fix_node(run_id))
    g.add_node("verify", verify_node)
    g.add_node("rollback", make_rollback_node(run_id))
    g.add_node("escalate", make_escalate_node(run_id))
    g.add_node("resolve", make_resolve_node(run_id))
    g.add_edge(START, "runbook")
    g.add_edge("runbook", "fix")
    g.add_edge("fix", "verify")
    g.add_conditional_edges("verify", route_after_verify)
    g.add_edge("rollback", "escalate")
    g.add_edge("escalate", "resolve")
    g.add_edge("resolve", END)
    return g


def open_ticket(ticket_id: str, device: str, reachable: bool, fixable_by: str) -> None:
    """Test/demo helper: seed a device and its ticket."""
    with psycopg.connect(DATABASE_URL) as conn:
        ensure_fleet(conn)
        conn.execute(
            "INSERT INTO device_state (device, reachable, fixable_by)"
            " VALUES (%s, %s, %s) ON CONFLICT (device) DO UPDATE"
            " SET reachable = %s, fixable_by = %s, healthy = false,"
            " vpn_profile = 'corp-v1'",
            (device, reachable, fixable_by, reachable, fixable_by),
        )
        conn.execute(
            "INSERT INTO itops_tickets (ticket_id, device) VALUES (%s, %s)"
            " ON CONFLICT (ticket_id) DO NOTHING",
            (ticket_id, device),
        )
        conn.commit()

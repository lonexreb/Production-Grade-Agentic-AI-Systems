"""IT Ops: the failure-recovery ladder — fallback, rollback, escalation."""

import uuid

import psycopg

from apps.itops import agent as ops
from runtime import Runtime
from runtime.config import DATABASE_URL


def _setup(reachable: bool, fixable_by: str) -> tuple[str, str, str]:
    uid = uuid.uuid4().hex[:8]
    run_id, ticket, device = f"ops-{uid}", f"T-{uid}", f"laptop-{uid}"
    ops.open_ticket(ticket, device, reachable, fixable_by)
    return run_id, ticket, device


def _device(device: str) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        p, h = conn.execute(
            "SELECT vpn_profile, healthy FROM device_state WHERE device = %s", (device,)
        ).fetchone()
        return {"profile": p, "healthy": h}


def _ticket_status(ticket: str) -> str:
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(
            "SELECT status FROM itops_tickets WHERE ticket_id = %s", (ticket,)
        ).fetchone()[0]


def test_happy_path_restart_fixes_it():
    run_id, ticket, device = _setup(reachable=True, fixable_by="restart")
    final = Runtime().run(ops.build_graph(run_id),
                          {"ticket_id": ticket, "device": device}, run_id)
    assert "resolved automatically (restart_vpn)" in final["response"]
    assert _ticket_status(ticket) == "resolved"


def test_fallback_reset_fixes_unreachable_device():
    run_id, ticket, device = _setup(reachable=False, fixable_by="reset")
    final = Runtime().run(ops.build_graph(run_id),
                          {"ticket_id": ticket, "device": device}, run_id)
    # restart_vpn raised (unreachable) -> router fell back to reset_profile
    assert "resolved automatically (reset_profile)" in final["response"]
    assert _ticket_status(ticket) == "resolved"


def test_rollback_and_escalation_when_nothing_fixes_it():
    run_id, ticket, device = _setup(reachable=False, fixable_by="none")
    rt = Runtime()
    result = rt.run(ops.build_graph(run_id),
                    {"ticket_id": ticket, "device": device}, run_id)

    # fallback reset applied (profile changed), verify failed, rollback restored it
    assert "__interrupt__" in result
    assert _device(device)["profile"] == "corp-v1"

    with psycopg.connect(DATABASE_URL) as conn:
        status = conn.execute(
            "SELECT status FROM side_effects WHERE run_id = %s", (run_id,)
        ).fetchone()[0]
    assert status == "compensated"

    final = rt.resume(ops.build_graph(run_id), run_id,
                      decision={"approved": True, "by": "lead@corp.example",
                                "assign_to": "tech-north"})
    assert "escalated to tech-north" in final["response"]
    assert _ticket_status(ticket) == "escalated"

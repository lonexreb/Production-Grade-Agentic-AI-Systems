"""IT Ops eval harness: seed the fleet per case, run the real graph, observe."""

import uuid

import psycopg

from apps.itops.agent import build_graph, open_ticket
from runtime import Runtime
from runtime.config import DATABASE_URL


def run_case(case: dict) -> dict:
    uid = uuid.uuid4().hex[:8]
    run_id, ticket, device = f"eval-ops-{uid}", f"T-{uid}", f"laptop-{uid}"
    inp = case["input"]
    open_ticket(ticket, device, inp["reachable"], inp["fixable_by"])

    rt = Runtime()
    result = rt.run(build_graph(run_id), {"ticket_id": ticket, "device": device}, run_id)
    touches = 0
    if "__interrupt__" in result:
        touches = 1
        result = rt.resume(build_graph(run_id), run_id, decision=inp.get("decision"))

    with psycopg.connect(DATABASE_URL) as conn:
        ticket_status = conn.execute(
            "SELECT status FROM itops_tickets WHERE ticket_id = %s", (ticket,)
        ).fetchone()[0]
        profile = conn.execute(
            "SELECT vpn_profile FROM device_state WHERE device = %s", (device,)
        ).fetchone()[0]
        compensated = conn.execute(
            "SELECT count(*) FROM side_effects"
            " WHERE run_id = %s AND status = 'compensated'", (run_id,),
        ).fetchone()[0]

    return {
        "response": result.get("response", ""),
        "human_touches": touches,
        "ticket_status": ticket_status,
        "profile": profile,
        "compensated_effects": compensated,
    }

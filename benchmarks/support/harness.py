"""Support eval harness: one case through the real graph, observed values out."""

import uuid

import psycopg

from apps.support.agent import build_graph
from runtime import Runtime, memory
from runtime.config import DATABASE_URL


def run_case(case: dict) -> dict:
    uid = uuid.uuid4().hex[:8]
    run_id, customer = f"eval-sup-{uid}", f"cust-{uid}"
    inp = case["input"]

    if inp.get("prior_refunds"):
        with psycopg.connect(DATABASE_URL) as conn:
            memory.ensure_schema(conn)
            memory.write_episode(conn, "support", "seed",
                                 f"refund {customer} $20 granted", {"ok": True})

    rt = Runtime()
    result = rt.run(build_graph(run_id), {"email": inp["email"], "customer": customer},
                    run_id)
    touches = 0
    if "__interrupt__" in result:
        touches = 1
        result = rt.resume(build_graph(run_id), run_id, decision=inp.get("decision"))

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS refunds"
                     " (id serial PRIMARY KEY, customer text, amount numeric)")
        conn.commit()
        refunds = conn.execute(
            "SELECT count(*) FROM refunds WHERE customer = %s", (customer,)
        ).fetchone()[0]

    return {"human_touches": touches, "refunds": refunds,
            "response": result.get("response", "")}

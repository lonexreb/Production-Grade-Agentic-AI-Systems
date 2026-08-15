"""HR eval harness: run one case through the real graph, return observed values."""

import uuid

import psycopg

from apps.hr.agent import build_graph
from runtime import Runtime, audit
from runtime.config import DATABASE_URL


def run_case(case: dict) -> dict:
    run_id = f"eval-hr-{uuid.uuid4().hex[:8]}"
    employee = f"{run_id}@corp.example"
    rt = Runtime()

    result = rt.run(build_graph(run_id),
                    {"email": case["input"]["email"], "employee": employee}, run_id)
    paused = "__interrupt__" in result
    final = rt.resume(build_graph(run_id), run_id,
                      decision=case["input"]["decision"]) if paused else result

    with psycopg.connect(DATABASE_URL) as conn:
        payroll_rows = conn.execute(
            "SELECT count(*) FROM payroll_changes WHERE employee = %s", (employee,)
        ).fetchone()[0]
        events = [e["event"] for e in audit.for_run(conn, run_id)]

    return {
        "paused": paused,
        "response": final.get("response", ""),
        "payroll_rows": payroll_rows,
        "events": events,
    }

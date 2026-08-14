"""HR Agent: pause-for-approval, resume-with-decision, audit trail, enforcement."""

import uuid

import psycopg
import pytest

from apps.hr.agent import build_graph
from runtime import Runtime, audit
from runtime.config import DATABASE_URL
from runtime.tools import ApprovalRequired, Tool, ToolRouter

EMAIL = {"email": "please update my direct deposit", "employee": "alex@corp.example"}


def _payroll_rows(run_employee: str) -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS payroll_changes"
            " (id serial PRIMARY KEY, employee text, detail text)"
        )
        conn.commit()
        return conn.execute(
            "SELECT count(*) FROM payroll_changes WHERE employee = %s", (run_employee,)
        ).fetchone()[0]


def test_approve_tier_enforced_at_router():
    r = ToolRouter()
    r.register(Tool(name="pay", fn=lambda: "paid", risk_tier="approve"))
    with pytest.raises(ApprovalRequired):
        r.call("pay")


def test_approved_flow():
    run_id = f"hr-test-{uuid.uuid4().hex[:8]}"
    employee = f"{run_id}@corp.example"
    rt = Runtime()

    result = rt.run(build_graph(run_id), {**EMAIL, "employee": employee}, run_id)
    assert "__interrupt__" in result

    with psycopg.connect(DATABASE_URL) as conn:
        status = conn.execute(
            "SELECT status FROM runs WHERE run_id = %s", (run_id,)
        ).fetchone()[0]
    assert status == "paused"

    final = rt.resume(build_graph(run_id), run_id,
                      decision={"approved": True, "by": "mgr@corp.example"})
    assert "completed" in final["response"]
    assert _payroll_rows(employee) == 1

    with psycopg.connect(DATABASE_URL) as conn:
        events = [e["event"] for e in audit.for_run(conn, run_id)]
    assert events == ["approval_requested", "approval_granted", "tool_call",
                      "notification_sent"]


def test_rejected_flow_makes_no_payroll_change():
    run_id = f"hr-test-{uuid.uuid4().hex[:8]}"
    employee = f"{run_id}@corp.example"
    rt = Runtime()

    rt.run(build_graph(run_id), {**EMAIL, "employee": employee}, run_id)
    final = rt.resume(build_graph(run_id), run_id,
                      decision={"approved": False, "by": "mgr@corp.example",
                                "note": "unverified bank"})
    assert "declined" in final["response"]
    assert _payroll_rows(employee) == 0

    with psycopg.connect(DATABASE_URL) as conn:
        events = [e["event"] for e in audit.for_run(conn, run_id)]
    assert "approval_rejected" in events
    assert "tool_call" not in events

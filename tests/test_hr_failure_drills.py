"""Phase 2 failure drills: the approval flow under adversarial conditions.

Drill 1: crash during approval wait — 'paused' lives in Postgres, so a fresh
         process (nothing shared in memory) can resume with the decision.
Drill 2: payroll API down transiently — router retries inside the budget,
         effect lands exactly once.
Drill 3: payroll API down hard — run is marked 'failed', no payroll change.
"""

import uuid

import psycopg
import pytest

from apps.hr import agent as hr
from runtime import Runtime
from runtime.config import DATABASE_URL
from runtime.tools import Tool, ToolError

EMAIL = {"email": "please update my direct deposit"}
APPROVE = {"approved": True, "by": "mgr@corp.example"}


def _payroll_rows(employee: str) -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(
            "SELECT count(*) FROM payroll_changes WHERE employee = %s", (employee,)
        ).fetchone()[0]


def _status(run_id: str) -> str:
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(
            "SELECT status FROM runs WHERE run_id = %s", (run_id,)
        ).fetchone()[0]


def test_drill_crash_during_approval_wait():
    """Pause, then resume from a completely fresh Runtime + rebuilt graph —
    everything needed to finish the run must live in Postgres, not memory."""
    run_id = f"drill-{uuid.uuid4().hex[:8]}"
    employee = f"{run_id}@corp.example"

    Runtime().run(hr.build_graph(run_id), {**EMAIL, "employee": employee}, run_id)
    assert _status(run_id) == "paused"

    # "process restart": new Runtime, freshly built graph, zero shared objects
    final = Runtime().resume(hr.build_graph(run_id), run_id, decision=APPROVE)
    assert "completed" in final["response"]
    assert _status(run_id) == "done"
    assert _payroll_rows(employee) == 1


def test_drill_payroll_api_transient_outage(monkeypatch):
    """Tool fails twice, succeeds on the third try — inside the retry budget."""
    run_id = f"drill-{uuid.uuid4().hex[:8]}"
    employee = f"{run_id}@corp.example"
    attempts = []

    def flaky_payroll(employee: str, detail: str) -> dict:
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("payroll API 503")
        return hr._update_payroll(employee, detail)

    monkeypatch.setitem(
        hr.router.tools, "update_payroll",
        Tool(name="update_payroll", fn=flaky_payroll, risk_tier="approve", max_retries=2),
    )

    rt = Runtime()
    rt.run(hr.build_graph(run_id), {**EMAIL, "employee": employee}, run_id)
    final = rt.resume(hr.build_graph(run_id), run_id, decision=APPROVE)

    assert "completed" in final["response"]
    assert len(attempts) == 3
    assert _payroll_rows(employee) == 1


def test_drill_payroll_api_hard_down(monkeypatch):
    """Retry budget exhausted -> run marked 'failed', zero payroll changes."""
    run_id = f"drill-{uuid.uuid4().hex[:8]}"
    employee = f"{run_id}@corp.example"

    def dead_payroll(employee: str, detail: str) -> dict:
        raise ConnectionError("payroll API down")

    monkeypatch.setitem(
        hr.router.tools, "update_payroll",
        Tool(name="update_payroll", fn=dead_payroll, risk_tier="approve", max_retries=1),
    )

    rt = Runtime()
    rt.run(hr.build_graph(run_id), {**EMAIL, "employee": employee}, run_id)
    with pytest.raises(ToolError):
        rt.resume(hr.build_graph(run_id), run_id, decision=APPROVE)

    assert _status(run_id) == "failed"
    assert _payroll_rows(employee) == 0

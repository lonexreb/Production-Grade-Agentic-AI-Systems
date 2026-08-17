"""Support agent: risk-routed refunds, concurrency isolation, shadow guarantees."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg

from apps.support import agent as sup
from runtime import Runtime, memory, shadow
from runtime.config import DATABASE_URL


def _refunds(customer: str) -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS refunds"
            " (id serial PRIMARY KEY, customer text, amount numeric)"
        )
        conn.commit()
        return conn.execute(
            "SELECT count(*) FROM refunds WHERE customer = %s", (customer,)
        ).fetchone()[0]


def _email(amount: float) -> str:
    return f"I want a refund of ${amount:g} for my order"


def test_small_refund_clears_on_policy():
    customer = f"cust-{uuid.uuid4().hex[:8]}"
    run_id = f"sup-{uuid.uuid4().hex[:8]}"
    final = Runtime().run(sup.build_graph(run_id),
                          {"email": _email(20), "customer": customer}, run_id)
    assert "__interrupt__" not in final
    assert "refund is on the way" in final["response"]
    assert _refunds(customer) == 1


def test_large_refund_needs_human():
    customer = f"cust-{uuid.uuid4().hex[:8]}"
    run_id = f"sup-{uuid.uuid4().hex[:8]}"
    rt = Runtime()
    result = rt.run(sup.build_graph(run_id),
                    {"email": _email(500), "customer": customer}, run_id)
    assert "__interrupt__" in result
    final = rt.resume(sup.build_graph(run_id), run_id,
                      decision={"approved": False, "by": "lead@corp.example"})
    assert "declined" in final["response"]
    assert _refunds(customer) == 0


def test_repeat_refunder_gated_even_for_small_amount():
    customer = f"cust-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(DATABASE_URL) as conn:
        memory.ensure_schema(conn)
        memory.write_episode(conn, sup.APP, "old",
                             f"refund {customer} $20 granted", {"ok": True})
    run_id = f"sup-{uuid.uuid4().hex[:8]}"
    result = Runtime().run(sup.build_graph(run_id),
                           {"email": _email(10), "customer": customer}, run_id)
    assert "__interrupt__" in result


def test_concurrent_runs_stay_isolated():
    """8 refund runs in parallel: every run completes and owns exactly one refund."""
    customers = [f"cust-{uuid.uuid4().hex[:8]}" for _ in range(8)]

    def one(customer: str) -> dict:
        run_id = f"sup-{customer}"
        return Runtime().run(sup.build_graph(run_id),
                             {"email": _email(15), "customer": customer}, run_id)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, customers))

    assert all("refund is on the way" in r["response"] for r in results)
    assert all(_refunds(c) == 1 for c in customers)


def test_shadow_run_makes_no_real_refund():
    customer = f"cust-{uuid.uuid4().hex[:8]}"
    run_id = f"shadow-{uuid.uuid4().hex[:8]}"
    stubs = {"issue_refund": lambda **kw: {"refunded": kw["amount"], "customer": kw["customer"]},
             "send_reply": {"ok": True}}
    with shadow.shadowed(sup, stubs):
        final = Runtime().run(sup.build_graph(run_id),
                              {"email": _email(20), "customer": customer}, run_id)
    assert "refund is on the way" in final["response"]  # behaved identically...
    assert _refunds(customer) == 0                       # ...but touched nothing
    assert [c["tool"] for c in shadow.calls_for(run_id)] == ["issue_refund", "send_reply"]


def test_shadow_compare_shows_policy_change_impact():
    """Candidate policy (limit 100) auto-clears a $75 refund the baseline gates."""
    customer = f"cust-{uuid.uuid4().hex[:8]}"
    stubs = {"issue_refund": lambda **kw: {"refunded": kw["amount"]},
             "send_reply": {"ok": True}}
    observed = {}
    for label, limit in [("baseline", 50.0), ("candidate", 100.0)]:
        run_id = f"shadow-{label}-{uuid.uuid4().hex[:8]}"
        with shadow.shadowed(sup, stubs):
            result = Runtime().run(sup.build_graph(run_id, refund_limit=limit),
                                   {"email": _email(75), "customer": customer}, run_id)
        observed[label] = {"paused": "__interrupt__" in result}

    diff = shadow.compare(observed["baseline"], observed["candidate"])
    assert diff["changed"]
    assert diff["deltas"]["paused"] == {"baseline": True, "candidate": False}
    assert _refunds(customer) == 0  # neither version touched the world
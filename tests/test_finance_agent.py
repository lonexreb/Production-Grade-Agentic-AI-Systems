"""Finance Agent: memory changes behavior — first invoice pauses, repeat doesn't."""

import uuid

import psycopg
import pytest

from apps.finance import agent as fin
from runtime import Runtime, audit, memory
from runtime.config import DATABASE_URL

APPROVE = {"approved": True, "by": "cfo@corp.example"}


def _payments(vendor: str) -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS payments"
            " (id serial PRIMARY KEY, vendor text, amount numeric, memo text)"
        )
        conn.commit()
        return conn.execute(
            "SELECT count(*) FROM payments WHERE vendor = %s", (vendor,)
        ).fetchone()[0]


def _invoice(vendor: str, amount: float = 250.0) -> dict:
    return {"invoice": {"vendor": vendor, "amount": amount, "memo": "services"}}


def test_first_invoice_needs_human_second_clears_on_policy():
    vendor = f"acme-{uuid.uuid4().hex[:8]}"
    rt = Runtime()

    # invoice 1: unknown vendor -> pauses for a human
    r1 = f"fin-{uuid.uuid4().hex[:8]}"
    result = rt.run(fin.build_graph(r1), _invoice(vendor), r1)
    assert "__interrupt__" in result
    final = rt.resume(fin.build_graph(r1), r1, decision=APPROVE)
    assert "paid" in final["response"]
    assert _payments(vendor) == 1

    # invoice 2: vendor now a semantic-memory fact -> zero human touches
    r2 = f"fin-{uuid.uuid4().hex[:8]}"
    final2 = rt.run(fin.build_graph(r2), _invoice(vendor), r2)
    assert "__interrupt__" not in final2
    assert "policy:verified-vendor-under-limit" in final2["response"]
    assert _payments(vendor) == 2

    with psycopg.connect(DATABASE_URL) as conn:
        events = [e["event"] for e in audit.for_run(conn, r2)]
    assert "approval_granted" in events  # policy approval is audited too


def test_large_invoice_always_sees_human_even_for_verified_vendor():
    vendor = f"acme-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(DATABASE_URL) as conn:
        memory.ensure_schema(conn)
        memory.remember_fact(conn, fin.APP, f"vendor:{vendor}", "verified")

    run_id = f"fin-{uuid.uuid4().hex[:8]}"
    result = Runtime().run(fin.build_graph(run_id), _invoice(vendor, 50_000.0), run_id)
    assert "__interrupt__" in result


def test_fraud_episode_forces_human_gate():
    vendor = f"acme-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(DATABASE_URL) as conn:
        memory.ensure_schema(conn)
        memory.remember_fact(conn, fin.APP, f"vendor:{vendor}", "verified")
        memory.write_episode(conn, fin.APP, "old-run",
                             f"invoice {vendor} fraud chargeback", {"ok": False})

    run_id = f"fin-{uuid.uuid4().hex[:8]}"
    result = Runtime().run(fin.build_graph(run_id), _invoice(vendor), run_id)
    assert "__interrupt__" in result  # verified vendor, but history says look closer


def test_rejected_invoice_pays_nothing_and_vendor_stays_unverified():
    vendor = f"acme-{uuid.uuid4().hex[:8]}"
    rt = Runtime()
    run_id = f"fin-{uuid.uuid4().hex[:8]}"
    rt.run(fin.build_graph(run_id), _invoice(vendor), run_id)
    final = rt.resume(fin.build_graph(run_id), run_id,
                      decision={"approved": False, "by": "cfo@corp.example"})
    assert "rejected" in final["response"]
    assert _payments(vendor) == 0
    with psycopg.connect(DATABASE_URL) as conn:
        assert memory.facts_for(conn, fin.APP, f"vendor:{vendor}") == []
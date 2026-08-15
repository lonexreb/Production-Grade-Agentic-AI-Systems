"""Finance eval harness: two invoices per case — measures the memory benefit.

Observed values include human_touches_first / human_touches_second: the memory
benchmark is second == 0 for a small repeat invoice from an approved vendor.
"""

import uuid

import psycopg

from apps.finance.agent import build_graph
from runtime import Runtime
from runtime.config import DATABASE_URL


def _run_invoice(rt: Runtime, vendor: str, amount: float, decision: dict | None) -> dict:
    run_id = f"eval-fin-{uuid.uuid4().hex[:8]}"
    invoice = {"invoice": {"vendor": vendor, "amount": amount, "memo": "eval"}}
    result = rt.run(build_graph(run_id), invoice, run_id)
    touches = 0
    if "__interrupt__" in result:
        touches = 1
        result = rt.resume(build_graph(run_id), run_id, decision=decision)
    return {"touches": touches, "response": result.get("response", "")}


def run_case(case: dict) -> dict:
    vendor = f"eval-{uuid.uuid4().hex[:8]}"
    rt = Runtime()
    inp = case["input"]

    first = _run_invoice(rt, vendor, inp["amount"], inp.get("decision"))
    second = _run_invoice(rt, vendor, inp.get("second_amount", inp["amount"]),
                          inp.get("decision"))

    with psycopg.connect(DATABASE_URL) as conn:
        payments = conn.execute(
            "SELECT count(*) FROM payments WHERE vendor = %s", (vendor,)
        ).fetchone()[0]

    return {
        "human_touches_first": first["touches"],
        "human_touches_second": second["touches"],
        "payments": payments,
        "response": second["response"],
    }

"""Finance Agent demo: memory turns the second invoice into a zero-touch payment.

Run: python -m apps.finance.demo
"""

import uuid

import psycopg

from apps.finance.agent import build_graph
from runtime import Runtime, audit, otel
from runtime.config import DATABASE_URL


def show_trail(run_id: str) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        for e in audit.for_run(conn, run_id):
            print(f"  {e['actor']}: {e['event']}")


def main() -> None:
    otel.configure()
    vendor = f"acme-{uuid.uuid4().hex[:6]}"
    rt = Runtime()
    invoice = {"invoice": {"vendor": vendor, "amount": 420.0, "memo": "consulting"}}

    print(f"=== invoice 1 from {vendor}: unknown vendor ===")
    r1 = f"fin-{uuid.uuid4().hex[:8]}"
    result = rt.run(build_graph(r1), invoice, r1)
    print(f"paused: {result['__interrupt__'][0].value['question']}")
    final = rt.resume(build_graph(r1), r1,
                      decision={"approved": True, "by": "cfo@corp.example"})
    print(f"outcome: {final['response']}")
    show_trail(r1)

    print(f"\n=== invoice 2 from {vendor}: vendor remembered ===")
    r2 = f"fin-{uuid.uuid4().hex[:8]}"
    final2 = rt.run(build_graph(r2), invoice, r2)
    assert "__interrupt__" not in final2
    print(f"outcome: {final2['response']}")
    show_trail(r2)

    print("\nhuman touches: invoice 1 -> 1, invoice 2 -> 0 (memory at work)")


if __name__ == "__main__":
    main()

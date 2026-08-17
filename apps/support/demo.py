"""Support demo: risk-routed refunds + a shadow evaluation of a policy change.

Run: python -m apps.support.demo
"""

import uuid

from apps.support import agent as sup
from apps.support.agent import build_graph
from runtime import Runtime, otel, shadow

STUBS = {"issue_refund": lambda **kw: {"refunded": kw["amount"]},
         "send_reply": {"ok": True}}


def main() -> None:
    otel.configure()
    rt = Runtime()

    print("=== $20 refund: clears on policy, zero human touches ===")
    run_id = f"sup-{uuid.uuid4().hex[:8]}"
    final = rt.run(build_graph(run_id),
                   {"email": "I want a refund of $20 for my order",
                    "customer": f"cust-{uuid.uuid4().hex[:6]}"}, run_id)
    print(f"outcome: {final['response']}")

    print("\n=== $500 refund: pauses for a human ===")
    run_id = f"sup-{uuid.uuid4().hex[:8]}"
    result = rt.run(build_graph(run_id),
                    {"email": "I want a refund of $500 for my order",
                     "customer": f"cust-{uuid.uuid4().hex[:6]}"}, run_id)
    print(f"paused: {result['__interrupt__'][0].value['question']}")
    final = rt.resume(build_graph(run_id), run_id,
                      decision={"approved": True, "by": "lead@corp.example"})
    print(f"outcome: {final['response']}")

    print("\n=== shadow eval: what if the auto-refund limit were $100? ===")
    cases = [15.0, 75.0, 250.0]
    print(f"{'case':>8}  {'baseline ($50)':>16}  {'candidate ($100)':>17}")
    for amount in cases:
        observed = {}
        for label, limit in [("baseline", 50.0), ("candidate", 100.0)]:
            run_id = f"shadow-{label}-{uuid.uuid4().hex[:8]}"
            with shadow.shadowed(sup, STUBS):
                r = rt.run(build_graph(run_id, refund_limit=limit),
                           {"email": f"I want a refund of ${amount:g} for my order",
                            "customer": f"cust-shadow-{uuid.uuid4().hex[:6]}"}, run_id)
            observed[label] = "human gate" if "__interrupt__" in r else "auto"
        print(f"{f'${amount:g}':>8}  {observed['baseline']:>16}  {observed['candidate']:>17}")
    print("side effects during shadow: none (router double never calls real tools)")


if __name__ == "__main__":
    main()

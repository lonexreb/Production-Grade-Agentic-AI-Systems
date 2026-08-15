"""IT Ops demo: the failure-recovery ladder, one rung at a time.

  1. restart fixes it            -> resolved, zero human touches
  2. device unreachable          -> router falls back to profile reset -> resolved
  3. nothing fixes it            -> fix rolled back (saga), human decides

Run: python -m apps.itops.demo
"""

import uuid

import psycopg

from apps.itops.agent import build_graph, open_ticket
from runtime import Runtime, audit, otel
from runtime.config import DATABASE_URL


def show_trail(run_id: str) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        for e in audit.for_run(conn, run_id):
            print(f"  {e['actor']}: {e['event']}")


def scenario(title: str, reachable: bool, fixable_by: str, decision: dict | None) -> None:
    uid = uuid.uuid4().hex[:6]
    run_id, ticket, device = f"ops-{uid}", f"T-{uid}", f"laptop-{uid}"
    open_ticket(ticket, device, reachable, fixable_by)
    rt = Runtime()

    print(f"\n=== {title} ({device}) ===")
    result = rt.run(build_graph(run_id), {"ticket_id": ticket, "device": device}, run_id)
    if "__interrupt__" in result:
        print(f"paused: {result['__interrupt__'][0].value['question']}")
        result = rt.resume(build_graph(run_id), run_id, decision=decision)
    print(f"outcome: {result['response']}")
    show_trail(run_id)


def main() -> None:
    otel.configure()
    scenario("restart fixes it", reachable=True, fixable_by="restart", decision=None)
    scenario("unreachable -> fallback profile reset", reachable=False,
             fixable_by="reset", decision=None)
    scenario("nothing fixes it -> rollback + escalate", reachable=False,
             fixable_by="none",
             decision={"approved": True, "by": "lead@corp.example",
                       "assign_to": "tech-north"})


if __name__ == "__main__":
    main()

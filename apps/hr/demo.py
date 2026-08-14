"""HR Agent demo: approval and rejection flows, with the audit trail printed.

The run PAUSES at the approval gate (status 'paused' in the runs table, fully
checkpointed) and resumes with the manager's decision — here in-process, in
production from an approval API in a different process, days later.

Run: python -m apps.hr.demo
"""

import uuid

import psycopg

from apps.hr.agent import build_graph
from runtime import Runtime, audit, otel
from runtime.config import DATABASE_URL


def show_trail(run_id: str) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        for entry in audit.for_run(conn, run_id):
            print(f"  [{entry['at']}] {entry['actor']}: {entry['event']}")


def scenario(title: str, decision: dict) -> None:
    run_id = f"hr-{uuid.uuid4().hex[:8]}"
    rt = Runtime()
    print(f"\n=== {title} (run {run_id}) ===")

    result = rt.run(build_graph(run_id), {
        "email": "Hi, I switched banks — please update my direct deposit.",
        "employee": "alex@corp.example",
    }, run_id)
    assert "__interrupt__" in result, "expected the run to pause for approval"
    print(f"paused for approval: {result['__interrupt__'][0].value['question']}")

    final = rt.resume(build_graph(run_id), run_id, decision=decision)
    print(f"outcome: {final['response']}")
    show_trail(run_id)


def main() -> None:
    otel.configure()
    scenario("manager approves", {"approved": True, "by": "manager@corp.example"})
    scenario("manager rejects",
             {"approved": False, "by": "manager@corp.example", "note": "unverified bank"})


if __name__ == "__main__":
    main()

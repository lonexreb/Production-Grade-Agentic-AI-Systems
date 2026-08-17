"""SWE Agent demo: fix a real failing test suite, gated on human merge approval.

Run: python -m apps.swe.demo
"""

import uuid

import psycopg

from apps.swe.agent import build_graph
from runtime import Runtime, audit, llm, otel
from runtime.config import DATABASE_URL


def main() -> None:
    otel.configure()
    assert llm.available(), "SWE agent needs ANTHROPIC_API_KEY (see .env.example)"
    run_id = f"swe-{uuid.uuid4().hex[:8]}"
    rt = Runtime()

    print(f"=== issue: implement divide() — 2 tests currently failing ===")
    result = rt.run(build_graph(run_id), {
        "issue": "Implement divide(a, b) in calculator.py. It must return a/b "
                 "and raise ValueError on division by zero.",
    }, run_id)

    pause = result["__interrupt__"][0].value
    print(f"paused: {pause['question']}")
    print(f"review: {pause['review']}")

    final = rt.resume(build_graph(run_id), run_id,
                      decision={"approved": True, "by": "maintainer@corp.example"})
    print(f"outcome: {final['response']}")

    with psycopg.connect(DATABASE_URL) as conn:
        for e in audit.for_run(conn, run_id):
            print(f"  {e['actor']}: {e['event']}")


if __name__ == "__main__":
    main()

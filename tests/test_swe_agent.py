"""SWE agent e2e: real LLM, real pytest, human merge gate. Skips without a key —
a coder agent without a model would be testing theater, and CI has no secrets."""

import uuid
from pathlib import Path

import psycopg
import pytest

from runtime import Runtime, audit, llm
from runtime.config import DATABASE_URL

pytestmark = pytest.mark.skipif(not llm.available(),
                                reason="SWE agent needs ANTHROPIC_API_KEY")


def test_swe_agent_fixes_failing_tests_and_merges():
    from apps.swe.agent import build_graph

    run_id = f"swe-test-{uuid.uuid4().hex[:8]}"
    rt = Runtime()

    result = rt.run(build_graph(run_id), {
        "issue": "Implement divide(a, b) in calculator.py. It must return a/b "
                 "and raise ValueError on division by zero.",
    }, run_id)
    assert "__interrupt__" in result, "must pause for human merge approval"

    final = rt.resume(build_graph(run_id), run_id,
                      decision={"approved": True, "by": "maintainer@test"})
    assert "merged as" in final["response"]

    ws = Path(final["workspace"])
    assert "def divide" in (ws / "calculator.py").read_text()
    assert (ws / "change.patch").exists()

    with psycopg.connect(DATABASE_URL) as conn:
        events = [e["event"] for e in audit.for_run(conn, run_id)]
    for required in ["plan_made", "code_written", "tests_run", "review_done",
                     "approval_granted", "tool_call"]:
        assert required in events

"""Live problem #1: LangGraph's HITL double-execution.

Reported by real users: side effects placed before interrupt() run AGAIN when
the node re-executes on resume — duplicate records, double writes.
  - forum.langchain.com/t/twice-execution-of-agent-when-using-the-interrupt/2964
  - blog.raed.dev/posts/langgraph-hitl/

Below: the naive node reproduces the bug on this very runtime (2 rows), then
the OpenAgentOS pattern — interrupt() first + execute_once — fixes it (1 row).

Run: python -m examples.live_problems.problem_1_hitl_double_execution
"""

import uuid
from typing import TypedDict

import psycopg

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from runtime import Runtime, execute_once, side_effects
from runtime.config import DATABASE_URL


class S(TypedDict, total=False):
    decision: dict
    done: bool


def _record(label: str) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS hitl_demo (id serial, label text)")
        conn.execute("INSERT INTO hitl_demo (label) VALUES (%s)", (label,))
        conn.commit()


def _rows(label: str) -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(
            "SELECT count(*) FROM hitl_demo WHERE label = %s", (label,)
        ).fetchone()[0]


def naive_graph(label: str) -> StateGraph:
    """The pattern users write first — and the bug they report."""

    def act_then_ask(state: S) -> S:
        _record(label)                       # side effect BEFORE the interrupt...
        decision = interrupt("approve?")     # ...node re-runs on resume -> effect repeats
        return {"decision": decision, "done": True}

    g = StateGraph(S)
    g.add_node("act_then_ask", act_then_ask)
    g.add_edge(START, "act_then_ask")
    g.add_edge("act_then_ask", END)
    return g


def runtime_graph(label: str, run_id: str) -> StateGraph:
    """The OpenAgentOS pattern: interrupt() first, effect behind an idempotency key."""

    def gate(state: S) -> S:
        decision = interrupt("approve?")     # FIRST statement -> re-run replays nothing
        with psycopg.connect(DATABASE_URL) as conn:
            side_effects.ensure_schema(conn)
            execute_once(conn, side_effects.make_key(run_id, "act"), run_id,
                         lambda: (_record(label), {"ok": True})[1])
        return {"decision": decision, "done": True}

    g = StateGraph(S)
    g.add_node("gate", gate)
    g.add_edge(START, "gate")
    g.add_edge("gate", END)
    return g


def main() -> None:
    rt = Runtime()

    print("=== the bug, reproduced (naive: effect before interrupt) ===")
    label = f"naive-{uuid.uuid4().hex[:8]}"
    rid = f"hitl-{label}"
    rt.run(naive_graph(label), {}, rid)                      # pauses; effect ran once
    rt.resume(naive_graph(label), rid, decision={"approved": True})  # node RE-RUNS
    print(f"rows written by ONE approved action: {_rows(label)}  <-- the duplicate\n")
    assert _rows(label) == 2

    print("=== the fix (interrupt first + execute_once) ===")
    label = f"fixed-{uuid.uuid4().hex[:8]}"
    rid = f"hitl-{label}"
    rt.run(runtime_graph(label, rid), {}, rid)
    rt.resume(runtime_graph(label, rid), rid, decision={"approved": True})
    print(f"rows written by ONE approved action: {_rows(label)}")
    assert _rows(label) == 1
    print("PASS: same framework, same interrupt — exactly one side effect")


if __name__ == "__main__":
    main()

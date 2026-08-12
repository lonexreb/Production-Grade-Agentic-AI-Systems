"""Watchdog: dead runs are detected via expired leases and revived from checkpoints."""

import uuid
from typing import TypedDict

import psycopg

from langgraph.graph import END, START, StateGraph
from runtime import Runtime, watchdog
from runtime.config import DATABASE_URL


class S(TypedDict, total=False):
    steps: list


def _append(name):
    def node(state: S) -> S:
        return {"steps": state.get("steps", []) + [name]}

    return node


def build(run_id: str = "") -> StateGraph:
    g = StateGraph(S)
    g.add_node("a", _append("a"))
    g.add_node("b", _append("b"))
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    return g


def test_completed_run_marked_done_and_not_dead():
    rt = Runtime()
    run_id = f"wd-{uuid.uuid4().hex[:8]}"
    rt.run(build(), {}, run_id)

    with psycopg.connect(DATABASE_URL) as conn:
        status = conn.execute(
            "SELECT status FROM runs WHERE run_id = %s", (run_id,)
        ).fetchone()[0]
    assert status == "done"
    assert run_id not in watchdog.Watchdog().dead_runs()


def test_expired_lease_detected_and_revived():
    rt = Runtime()
    run_id = f"wd-{uuid.uuid4().hex[:8]}"
    rt.run(build(), {}, run_id)

    # simulate a process death: force status back to 'running' with an expired lease
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE runs SET status = 'running',"
            " lease_expires_at = now() - interval '1 minute' WHERE run_id = %s",
            (run_id,),
        )
        conn.commit()

    wd = watchdog.Watchdog()
    assert run_id in wd.dead_runs()

    revived = wd.revive_dead(build)
    assert run_id in revived
    assert run_id not in wd.dead_runs()  # revival completed the run -> 'done'

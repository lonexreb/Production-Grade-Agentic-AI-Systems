"""Engine: a run that fails mid-graph resumes from the checkpoint, not the start."""

import uuid
from typing import TypedDict

import pytest

from langgraph.graph import END, START, StateGraph
from runtime import Runtime


class S(TypedDict, total=False):
    a_runs: int
    b_runs: int


executed = {"a": 0, "b": 0, "fail_once": True}


def node_a(state: S) -> S:
    executed["a"] += 1
    return {"a_runs": executed["a"]}


def node_b(state: S) -> S:
    if executed["fail_once"]:
        executed["fail_once"] = False
        raise RuntimeError("transient failure")
    executed["b"] += 1
    return {"b_runs": executed["b"]}


def build() -> StateGraph:
    g = StateGraph(S)
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    return g


def test_resume_skips_completed_nodes():
    executed.update({"a": 0, "b": 0, "fail_once": True})
    rt = Runtime()
    run_id = f"test-{uuid.uuid4().hex[:8]}"

    with pytest.raises(RuntimeError, match="transient failure"):
        rt.run(build(), {}, run_id)
    assert executed["a"] == 1

    final = rt.resume(build(), run_id)
    assert executed["a"] == 1, "node a must NOT re-run after resume"
    assert final["b_runs"] == 1

    hist = rt.history(run_id)
    assert len(hist) >= 2
    replayed = rt.replay(run_id, hist[0]["checkpoint_id"])
    assert replayed.get("b_runs") == 1

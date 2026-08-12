"""Walking-skeleton demo agent: plan -> act -> verify -> respond.

The `act` node performs a real side effect (a Postgres insert) through the tool
router, guarded by an idempotency key. Set OAOS_CRASH=after-effect to kill the
process (kill -9 style) right after the effect executes but BEFORE the node
completes — the worst-case crash window. Resuming the same run_id must finish
the run with exactly one effect row. That is Phase 1's acceptance test.

Run:    python -m apps.demo.agent <run_id>
Resume: python -m apps.demo.agent <run_id> --resume
"""

import os
import sys
from typing import TypedDict

import psycopg

from runtime import Runtime, Tool, ToolRouter, execute_once, otel, side_effects
from runtime.config import DATABASE_URL
from langgraph.graph import END, START, StateGraph


class DemoState(TypedDict, total=False):
    request: str
    plan: str
    effect_result: dict
    verified: bool
    response: str


def _send_greeting(for_run: str, message: str) -> dict:
    """The side effect: insert one row. Stands in for a payroll call / payment.

    Note: named `for_run` because the router reserves `run_id` for tracing and
    does not forward it to the tool function.
    """
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS demo_effects"
            " (id serial PRIMARY KEY, run_id text, message text)"
        )
        conn.execute(
            "INSERT INTO demo_effects (run_id, message) VALUES (%s, %s)",
            (for_run, message),
        )
        conn.commit()
    return {"sent": message}


router = ToolRouter()
router.register(Tool(name="send_greeting", fn=_send_greeting, timeout_s=10))


def plan_node(state: DemoState) -> DemoState:
    # ponytail: deterministic planner; swap in an LLM call (optional `llm` extra)
    # when planning quality matters — crash-resume correctness doesn't need it.
    return {"plan": f"greet the requester: {state['request']}"}


def make_act_node(run_id: str):
    def act_node(state: DemoState) -> DemoState:
        with psycopg.connect(DATABASE_URL) as conn:
            side_effects.ensure_schema(conn)
            key = side_effects.make_key(run_id, "act")
            result = execute_once(
                conn, key, run_id,
                lambda: router.call(
                    "send_greeting", run_id=run_id, for_run=run_id, message=state["plan"]
                ),
            )
        if os.environ.get("OAOS_CRASH") == "after-effect":
            print("[demo] simulating hard crash after side effect", flush=True)
            os._exit(137)
        return {"effect_result": result}

    return act_node


def verify_node_factory(run_id: str):
    def verify_node(state: DemoState) -> DemoState:
        with psycopg.connect(DATABASE_URL) as conn:
            count = conn.execute(
                "SELECT count(*) FROM demo_effects WHERE run_id = %s", (run_id,)
            ).fetchone()[0]
        if count != 1:
            raise RuntimeError(f"expected exactly 1 effect row, found {count}")
        return {"verified": True}

    return verify_node


def respond_node(state: DemoState) -> DemoState:
    return {"response": f"done: {state['effect_result']['sent']} (verified)"}


def build_graph(run_id: str) -> StateGraph:
    g = StateGraph(DemoState)
    g.add_node("plan", plan_node)
    g.add_node("act", make_act_node(run_id))
    g.add_node("verify", verify_node_factory(run_id))
    g.add_node("respond", respond_node)
    g.add_edge(START, "plan")
    g.add_edge("plan", "act")
    g.add_edge("act", "verify")
    g.add_edge("verify", "respond")
    g.add_edge("respond", END)
    return g


def main() -> None:
    otel.configure()
    run_id = sys.argv[1]
    resume = "--resume" in sys.argv
    rt = Runtime()
    graph = build_graph(run_id)
    if resume:
        final = rt.resume(graph, run_id)
    else:
        final = rt.run(graph, {"request": "hello from OpenAgentOS"}, run_id)
    print(f"[demo] final state: {final}")


if __name__ == "__main__":
    main()

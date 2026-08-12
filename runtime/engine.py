"""Module 1: durable workflow engine — LangGraph + PostgresSaver.

One thread per run (thread_id = run_id). State checkpoints at every superstep.
A killed process resumes by calling run() again with the same run_id and input=None.
"""

from dataclasses import dataclass

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph

from runtime import config, otel, watchdog


@dataclass(frozen=True)
class Runtime:
    db_url: str = config.DATABASE_URL

    def _config(self, run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}}

    def run(self, builder: StateGraph, input: dict | None, run_id: str) -> dict:
        """Start a run, or resume it from the last checkpoint when input is None.

        The run is registered in the `runs` table and its lease heartbeats while
        the graph executes; if this process dies, the watchdog revives the run.
        """
        with psycopg.connect(self.db_url) as conn:
            watchdog.register(conn, run_id)
        with PostgresSaver.from_conn_string(self.db_url) as saver:
            saver.setup()
            graph = builder.compile(checkpointer=saver)
            with otel.span(
                f"invoke_agent {run_id}",
                **{otel.ATTR_OPERATION: "invoke_agent", otel.ATTR_RUN_ID: run_id},
            ):
                try:
                    with watchdog.Heartbeat(self.db_url, run_id):
                        result = graph.invoke(input, self._config(run_id))
                except Exception:
                    with psycopg.connect(self.db_url) as conn:
                        watchdog.mark(conn, run_id, "failed")
                    raise
        with psycopg.connect(self.db_url) as conn:
            watchdog.mark(conn, run_id, "done")
        return result

    def resume(self, builder: StateGraph, run_id: str) -> dict:
        return self.run(builder, None, run_id)

    def history(self, run_id: str) -> list[dict]:
        """Checkpoints for a run, newest first: id, timestamp, state values."""
        with PostgresSaver.from_conn_string(self.db_url) as saver:
            return [
                {
                    "checkpoint_id": t.checkpoint["id"],
                    "ts": t.checkpoint["ts"],
                    "values": t.checkpoint.get("channel_values", {}),
                }
                for t in saver.list(self._config(run_id))
            ]

    def replay(self, run_id: str, checkpoint_id: str) -> dict:
        """State values as they were at a specific checkpoint (time travel / audit)."""
        with PostgresSaver.from_conn_string(self.db_url) as saver:
            t = saver.get_tuple(
                {"configurable": {"thread_id": run_id, "checkpoint_id": checkpoint_id}}
            )
            if t is None:
                raise KeyError(f"no checkpoint {checkpoint_id} for run {run_id}")
            return t.checkpoint.get("channel_values", {})

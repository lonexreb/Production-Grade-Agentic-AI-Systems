"""Module 2: idempotent side effects — the thing that makes resume SAFE.

Pattern: claim (insert 'pending') -> execute -> record ('done' + result).
On re-run with the same key:
  done    -> return the stored result, do NOT re-execute
  pending -> a previous attempt crashed between claim and record; the effect is
             ambiguous. We re-execute.
             # ponytail: at-least-once on the pending window; add a per-tool
             # reconciliation hook (query the external system) when a real
             # non-idempotent integration lands.
"""

import json
from typing import Any, Callable

import psycopg

DDL = """
CREATE TABLE IF NOT EXISTS side_effects (
    key        text PRIMARY KEY,
    run_id     text NOT NULL,
    status     text NOT NULL CHECK (status IN ('pending', 'done')),
    result     jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    done_at    timestamptz
);
"""


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(DDL)
    conn.commit()


def make_key(run_id: str, node: str, scope: str = "0") -> str:
    return f"{run_id}:{node}:{scope}"


def execute_once(conn: psycopg.Connection, key: str, run_id: str, fn: Callable[[], Any]) -> Any:
    """Execute fn at most once per key across crashes and resumes.

    Returns fn's (JSON-serializable) result — stored on first success, replayed after.
    """
    row = conn.execute(
        "SELECT status, result FROM side_effects WHERE key = %s", (key,)
    ).fetchone()

    if row and row[0] == "done":
        return row[1]

    if row is None:
        conn.execute(
            "INSERT INTO side_effects (key, run_id, status) VALUES (%s, %s, 'pending')"
            " ON CONFLICT (key) DO NOTHING",
            (key, run_id),
        )
        conn.commit()

    result = fn()

    conn.execute(
        "UPDATE side_effects SET status = 'done', result = %s, done_at = now()"
        " WHERE key = %s",
        (json.dumps(result), key),
    )
    conn.commit()
    return result

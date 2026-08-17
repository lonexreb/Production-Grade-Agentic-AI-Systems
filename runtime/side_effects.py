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

from runtime import schema

DDL = """
CREATE TABLE IF NOT EXISTS side_effects (
    key        text PRIMARY KEY,
    run_id     text NOT NULL,
    status     text NOT NULL,
    result     jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    done_at    timestamptz
);
ALTER TABLE side_effects DROP CONSTRAINT IF EXISTS side_effects_status_check;
ALTER TABLE side_effects ADD CONSTRAINT side_effects_status_check
    CHECK (status IN ('pending', 'done', 'compensated'));
"""
# 'compensated' = the effect was applied, then undone by compensate_run (saga
# rollback). The row stays — the history that something happened and was
# reversed is audit-relevant, and the key must never be reusable.


def ensure_schema(conn: psycopg.Connection) -> None:
    schema.apply_once(conn, "side_effects", DDL)


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


def compensate_run(
    conn: psycopg.Connection, run_id: str, handlers: dict[str, Callable[[Any], None]]
) -> list[str]:
    """Saga rollback: undo a run's completed effects in reverse order.

    handlers maps node name (the middle segment of the key) to an undo function
    receiving the stored result. Effects without a handler are skipped — not
    every effect is reversible, and pretending otherwise is worse than saying so.
    Returns the keys that were compensated.
    """
    rows = conn.execute(
        "SELECT key, result FROM side_effects"
        " WHERE run_id = %s AND status = 'done' ORDER BY done_at DESC",
        (run_id,),
    ).fetchall()

    compensated = []
    for key, result in rows:
        node = key.split(":")[1]
        undo = handlers.get(node)
        if undo is None:
            continue
        undo(result)
        conn.execute(
            "UPDATE side_effects SET status = 'compensated' WHERE key = %s", (key,)
        )
        conn.commit()
        compensated.append(key)
    return compensated

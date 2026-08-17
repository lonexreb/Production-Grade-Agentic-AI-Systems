"""Shared schema-setup guard: run a module's DDL once per process, serialized.

Concurrent runs re-executing idempotent DDL (constraint swaps, trigger
recreation) take conflicting ACCESS EXCLUSIVE locks and deadlock — found by
the 8-way concurrency stress test. pg_advisory_xact_lock serializes setup
across processes; the per-process memo makes repeat calls free.
"""

import threading

import psycopg

_LOCK_ID = 731_225  # arbitrary constant shared by all OpenAgentOS schema setup
_applied: set[str] = set()
_local_lock = threading.Lock()


def apply_once(conn: psycopg.Connection, name: str, ddl: str) -> None:
    with _local_lock:
        if name in _applied:
            return
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_ID,))
    conn.execute(ddl)
    conn.commit()  # releases the xact-scoped advisory lock
    with _local_lock:
        _applied.add(name)

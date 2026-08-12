"""Idempotency: the double-run test — one execution across repeated calls."""

import uuid

import psycopg
import pytest

from runtime import side_effects
from runtime.config import DATABASE_URL


@pytest.fixture
def conn():
    with psycopg.connect(DATABASE_URL) as c:
        side_effects.ensure_schema(c)
        yield c


def test_double_run_executes_once(conn):
    calls = []
    key = side_effects.make_key(uuid.uuid4().hex, "pay")

    def effect():
        calls.append(1)
        return {"paid": 100}

    r1 = side_effects.execute_once(conn, key, "run-a", effect)
    r2 = side_effects.execute_once(conn, key, "run-a", effect)

    assert len(calls) == 1
    assert r1 == {"paid": 100}
    assert r2 == {"paid": 100}  # replayed from storage, not re-executed


def test_pending_crash_window_reexecutes(conn):
    """Crash between claim and record leaves 'pending' -> re-execute on resume."""
    key = side_effects.make_key(uuid.uuid4().hex, "pay")
    conn.execute(
        "INSERT INTO side_effects (key, run_id, status) VALUES (%s, 'run-b', 'pending')",
        (key,),
    )
    conn.commit()

    r = side_effects.execute_once(conn, key, "run-b", lambda: {"paid": 1})
    assert r == {"paid": 1}
    status = conn.execute(
        "SELECT status FROM side_effects WHERE key = %s", (key,)
    ).fetchone()[0]
    assert status == "done"


def test_distinct_keys_both_execute(conn):
    run = uuid.uuid4().hex
    k1 = side_effects.make_key(run, "pay", scope="invoice-1")
    k2 = side_effects.make_key(run, "pay", scope="invoice-2")
    calls = []
    side_effects.execute_once(conn, k1, run, lambda: calls.append(1) or {"n": 1})
    side_effects.execute_once(conn, k2, run, lambda: calls.append(1) or {"n": 2})
    assert len(calls) == 2

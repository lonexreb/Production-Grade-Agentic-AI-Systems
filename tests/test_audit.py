"""Audit log: append works, history is ordered, and rewrites are impossible."""

import uuid

import psycopg
import pytest

from runtime import audit
from runtime.config import DATABASE_URL


@pytest.fixture
def conn():
    with psycopg.connect(DATABASE_URL) as c:
        audit.ensure_schema(c)
        yield c


def test_append_and_read_ordered(conn):
    run_id = f"audit-{uuid.uuid4().hex[:8]}"
    audit.append(conn, run_id, "agent", "started", {"n": 1})
    audit.append(conn, run_id, "mgr@corp", "approved", {"n": 2})

    trail = audit.for_run(conn, run_id)
    assert [e["event"] for e in trail] == ["started", "approved"]
    assert all(len(e["payload_hash"]) == 64 for e in trail)


def test_update_and_delete_rejected_by_database(conn):
    run_id = f"audit-{uuid.uuid4().hex[:8]}"
    audit.append(conn, run_id, "agent", "started", {})

    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("UPDATE audit_log SET event = 'tampered' WHERE run_id = %s", (run_id,))
    conn.rollback()

    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("DELETE FROM audit_log WHERE run_id = %s", (run_id,))
    conn.rollback()

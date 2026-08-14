"""Module 8: append-only audit log — who did what, when, for any run, forever.

Immutability is enforced by the database, not by convention: a trigger rejects
UPDATE and DELETE on audit_log, so even buggy runtime code cannot rewrite history.
"""

import hashlib
import json
from typing import Any

import psycopg

DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id           bigserial PRIMARY KEY,
    run_id       text NOT NULL,
    actor        text NOT NULL,            -- 'agent' or a human identity
    event        text NOT NULL,            -- e.g. 'tool_call', 'approval_granted'
    payload      jsonb NOT NULL,
    payload_hash text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_log_run_idx ON audit_log (run_id, id);

CREATE OR REPLACE FUNCTION audit_log_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_rewrite ON audit_log;
CREATE TRIGGER audit_log_no_rewrite
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
"""


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(DDL)
    conn.commit()


def append(
    conn: psycopg.Connection, run_id: str, actor: str, event: str, payload: dict[str, Any]
) -> None:
    body = json.dumps(payload, sort_keys=True)
    conn.execute(
        "INSERT INTO audit_log (run_id, actor, event, payload, payload_hash)"
        " VALUES (%s, %s, %s, %s, %s)",
        (run_id, actor, event, body, hashlib.sha256(body.encode()).hexdigest()),
    )
    conn.commit()


def for_run(conn: psycopg.Connection, run_id: str) -> list[dict[str, Any]]:
    """Full audit trail for a run, oldest first."""
    rows = conn.execute(
        "SELECT actor, event, payload, payload_hash, created_at"
        " FROM audit_log WHERE run_id = %s ORDER BY id",
        (run_id,),
    ).fetchall()
    return [
        {"actor": a, "event": e, "payload": p, "payload_hash": h, "at": str(t)}
        for a, e, p, h, t in rows
    ]

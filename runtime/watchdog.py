"""Module 1 (part 2): watchdog — supervisor-guaranteed resume.

LangGraph checkpoints are save-points; resume is caller-triggered. The watchdog
closes that gap: the engine registers every run in a `runs` table and heartbeats
a lease while the graph executes. A killed process stops heartbeating, its lease
expires, and `Watchdog.revive_dead()` re-invokes the run from its checkpoint.

# ponytail: single-process polling watchdog; move to a scheduled worker
# (cron/celery) when runs outlive one supervisor process.
"""

import os
import threading
from dataclasses import dataclass

import psycopg

from runtime import config

DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id           text PRIMARY KEY,
    status           text NOT NULL,
    lease_expires_at timestamptz NOT NULL,
    updated_at       timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_status_check;
ALTER TABLE runs ADD CONSTRAINT runs_status_check
    CHECK (status IN ('running', 'paused', 'done', 'failed'));
"""
# 'paused' = stopped at interrupt(), awaiting a human decision. No live process,
# no lease — and NOT dead: dead_runs() only looks at 'running'.

DEFAULT_LEASE_S = int(os.environ.get("OAOS_LEASE_S", "30"))


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(DDL)
    conn.commit()


def register(conn: psycopg.Connection, run_id: str, lease_s: int = DEFAULT_LEASE_S) -> None:
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO runs (run_id, status, lease_expires_at)"
        " VALUES (%s, 'running', now() + make_interval(secs => %s))"
        " ON CONFLICT (run_id) DO UPDATE SET status = 'running',"
        " lease_expires_at = now() + make_interval(secs => %s), updated_at = now()",
        (run_id, lease_s, lease_s),
    )
    conn.commit()


def mark(conn: psycopg.Connection, run_id: str, status: str) -> None:
    conn.execute(
        "UPDATE runs SET status = %s, updated_at = now() WHERE run_id = %s",
        (status, run_id),
    )
    conn.commit()


class Heartbeat:
    """Renews a run's lease on a daemon thread until stopped."""

    def __init__(self, db_url: str, run_id: str, lease_s: int = DEFAULT_LEASE_S):
        self.db_url, self.run_id, self.lease_s = db_url, run_id, lease_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._beat, daemon=True)

    def _beat(self) -> None:
        while not self._stop.wait(self.lease_s / 3):
            try:
                with psycopg.connect(self.db_url) as conn:
                    conn.execute(
                        "UPDATE runs SET lease_expires_at = now() + make_interval(secs => %s)"
                        " WHERE run_id = %s AND status = 'running'",
                        (self.lease_s, self.run_id),
                    )
                    conn.commit()
            except psycopg.Error:
                pass  # transient DB blip; the lease just doesn't renew this tick

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()


@dataclass(frozen=True)
class Watchdog:
    db_url: str = config.DATABASE_URL

    def dead_runs(self) -> list[str]:
        """Runs still marked 'running' whose lease has expired — the process died."""
        with psycopg.connect(self.db_url) as conn:
            ensure_schema(conn)
            rows = conn.execute(
                "SELECT run_id FROM runs"
                " WHERE status = 'running' AND lease_expires_at < now()"
            ).fetchall()
        return [r[0] for r in rows]

    def revive_dead(self, build_graph) -> list[str]:
        """Resume every dead run. build_graph: run_id -> StateGraph."""
        from runtime.engine import Runtime  # local import avoids a module cycle

        revived = []
        for run_id in self.dead_runs():
            Runtime(self.db_url).resume(build_graph(run_id), run_id)
            revived.append(run_id)
        return revived

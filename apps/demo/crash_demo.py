"""Phase 1 acceptance demo: crash mid-run, watchdog revives, exactly one side effect.

  1. Start a run that hard-crashes (exit 137) right after its side effect executes.
  2. Wait for its lease to expire; the watchdog detects the dead run and revives it.
  3. Assert the run completed AND the side effect happened exactly once.

Run: python -m apps.demo.crash_demo
"""

import os
import subprocess
import sys
import time
import uuid

import psycopg

from apps.demo.agent import build_graph
from runtime import watchdog
from runtime.config import DATABASE_URL

LEASE_S = 2  # short lease so the demo doesn't wait 30s for expiry


def main() -> None:
    run_id = f"crash-demo-{uuid.uuid4().hex[:8]}"
    env = dict(os.environ)

    print(f"=== 1. run {run_id} with crash injection ===")
    p = subprocess.run(
        [sys.executable, "-m", "apps.demo.agent", run_id],
        env={**env, "OAOS_CRASH": "after-effect", "OAOS_LEASE_S": str(LEASE_S)},
    )
    assert p.returncode == 137, f"expected crash exit 137, got {p.returncode}"
    print("process died mid-run, as intended")

    print(f"=== 2. watchdog detects the dead run and revives it ===")
    wd = watchdog.Watchdog()
    deadline = time.time() + LEASE_S * 5
    while run_id not in wd.dead_runs():
        assert time.time() < deadline, "lease never expired"
        time.sleep(0.5)
    print(f"dead run detected: {run_id}")
    revived = wd.revive_dead(build_graph)
    assert run_id in revived, f"watchdog did not revive {run_id}"

    print("=== 3. verify exactly one side effect ===")
    with psycopg.connect(DATABASE_URL) as conn:
        count = conn.execute(
            "SELECT count(*) FROM demo_effects WHERE run_id = %s", (run_id,)
        ).fetchone()[0]
    assert count == 1, f"expected 1 effect row, found {count}"
    print(f"PASS: crashed mid-run, resumed, completed, side effect executed once")


if __name__ == "__main__":
    main()

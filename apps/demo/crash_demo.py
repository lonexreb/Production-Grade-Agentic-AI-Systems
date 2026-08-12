"""Phase 1 acceptance demo: crash mid-run, resume, verify exactly one side effect.

  1. Start a run that hard-crashes (exit 137) right after its side effect executes.
  2. Resume the same run_id in a fresh process.
  3. Assert the run completed AND the side effect happened exactly once.

Run: python -m apps.demo.crash_demo
"""

import os
import subprocess
import sys
import uuid

import psycopg

from runtime.config import DATABASE_URL


def main() -> None:
    run_id = f"crash-demo-{uuid.uuid4().hex[:8]}"
    env = dict(os.environ)

    print(f"=== 1. run {run_id} with crash injection ===")
    p = subprocess.run(
        [sys.executable, "-m", "apps.demo.agent", run_id],
        env={**env, "OAOS_CRASH": "after-effect"},
    )
    assert p.returncode == 137, f"expected crash exit 137, got {p.returncode}"
    print("process died mid-run, as intended")

    print(f"=== 2. resume {run_id} in a fresh process ===")
    p = subprocess.run(
        [sys.executable, "-m", "apps.demo.agent", run_id, "--resume"],
        env=env, capture_output=True, text=True,
    )
    print(p.stdout)
    assert p.returncode == 0, f"resume failed: {p.stderr}"
    assert "done: greet the requester" in p.stdout, "run did not complete"

    print("=== 3. verify exactly one side effect ===")
    with psycopg.connect(DATABASE_URL) as conn:
        count = conn.execute(
            "SELECT count(*) FROM demo_effects WHERE run_id = %s", (run_id,)
        ).fetchone()[0]
    assert count == 1, f"expected 1 effect row, found {count}"
    print(f"PASS: crashed mid-run, resumed, completed, side effect executed once")


if __name__ == "__main__":
    main()

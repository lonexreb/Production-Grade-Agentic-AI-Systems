"""Module 7: offline evaluation — a regression gate, not a leaderboard.

Cases live in benchmarks/<app>/cases.jsonl. Each app exposes
run_case(case) -> dict of observed values; the runner compares observed
against the case's `expect` block:

  {"name": "...", "input": {...}, "expect": {"response_contains": "paid",
                                             "payments": 1, "paused_first": true}}

Comparison rules: `<key>_contains` does substring match on observed[<key>];
anything else is equality. Exit code 1 below the pass threshold — that is the
CI gate.

Run: python -m runtime.evals benchmarks/hr --threshold 1.0
"""

import argparse
import importlib
import json
import sys
from pathlib import Path


def check(observed: dict, expect: dict) -> list[str]:
    """Failure messages, empty when the case passes."""
    failures = []
    for key, want in expect.items():
        if key.endswith("_contains"):
            got = str(observed.get(key.removesuffix("_contains"), ""))
            if want not in got:
                failures.append(f"{key}: {want!r} not in {got!r}")
        elif observed.get(key) != want:
            failures.append(f"{key}: expected {want!r}, got {observed.get(key)!r}")
    return failures


def run_suite(bench_dir: Path) -> tuple[int, int]:
    cases = [json.loads(line) for line in
             (bench_dir / "cases.jsonl").read_text().splitlines() if line.strip()]
    app = importlib.import_module(f"benchmarks.{bench_dir.name}.harness")

    passed = 0
    for case in cases:
        failures = check(app.run_case(case), case["expect"])
        mark = "PASS" if not failures else "FAIL"
        print(f"[{mark}] {bench_dir.name}/{case['name']}")
        for f in failures:
            print(f"       {f}")
        passed += not failures
    return passed, len(cases)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bench_dir", type=Path)
    parser.add_argument("--threshold", type=float, default=1.0)
    args = parser.parse_args()

    passed, total = run_suite(args.bench_dir)
    rate = passed / total if total else 0.0
    print(f"\n{args.bench_dir.name}: {passed}/{total} passed ({rate:.0%},"
          f" threshold {args.threshold:.0%})")
    sys.exit(0 if rate >= args.threshold else 1)


if __name__ == "__main__":
    main()

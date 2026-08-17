"""LIVE CASE: the SWE agent fixes a real open GitHub issue in a real repo.

Issue: mgomezdev/themis#38 — "API keys: scope typo guard is an assert,
stripped under python -O". backend/app/auth.py guards require_scope() with
`assert scope in SCOPES` — which vanishes under `python -O`, silently
disabling the only typo check across 113 call sites.
https://github.com/mgomezdev/themis/issues/38

What happens here, live:
  1. clone the repo at the issue's branch
  2. assemble a workspace: the real `app` package + a failing test that encodes
     the issue's acceptance criteria (ValueError on bad scope, and the guard
     must SURVIVE `python -O` — proven via subprocess)
  3. run the SWE agent on the REAL issue text; the repo's code is the input,
     pytest is the judge, a human owns the merge
  4. produce the patch a maintainer could apply

Run: python -m examples.live_case_swe.run
"""

import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import psycopg

from apps.swe.agent import build_graph
from runtime import Runtime, audit, llm, otel
from runtime.config import DATABASE_URL

REPO = "https://github.com/mgomezdev/themis"
BRANCH = "claude/themis-api-key-management-43n491"   # the branch the issue targets
ISSUE = (
    "Issue mgomezdev/themis#38 — API keys: scope typo guard is an assert, "
    "stripped under python -O.\n"
    "app/auth.py uses `assert scope in SCOPES` as the only typo guard across "
    "all 113 require_scope(...) call sites. assert statements are stripped when "
    "Python runs with -O, silently disabling this check in that mode.\n"
    "Fix: in app/auth.py, replace the assert with an explicit "
    "`if scope not in SCOPES: raise ValueError(...)` so the guard can't be "
    "optimized away."
)

ISSUE_TEST = '''\
"""Acceptance test for themis#38 — written from the issue text, before the fix."""

import subprocess
import sys
from pathlib import Path

import pytest

from app.auth import SCOPES, require_scope


def test_known_scope_accepted():
    assert require_scope("jobs:read") is not None


def test_unknown_scope_raises_value_error():
    with pytest.raises(ValueError):
        require_scope("jobs:reed")   # the typo the guard exists to catch


def test_guard_survives_python_O():
    """The whole point of the issue: -O strips asserts. The guard must not be one."""
    code = "from app.auth import require_scope; require_scope('bogus:scope')"
    proc = subprocess.run([sys.executable, "-O", "-c", code],
                          cwd=Path(__file__).parent.parent,
                          capture_output=True, text=True)
    assert proc.returncode != 0, "guard vanished under -O — still an assert"
    assert "ValueError" in proc.stderr
'''


def prepare_source() -> Path:
    src = Path(tempfile.mkdtemp(prefix="themis-case-")) / "case"
    repo = src.parent / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", REPO, str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "--depth", "1",
                    "origin", BRANCH], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "FETCH_HEAD"], check=True)
    src.mkdir(parents=True)
    shutil.copytree(repo / "backend" / "app", src / "app",
                    ignore=shutil.ignore_patterns("__pycache__"))
    tests = src / "tests"
    tests.mkdir()
    (tests / "test_issue_38_scope_guard.py").write_text(ISSUE_TEST)
    return src


def main() -> None:
    otel.configure()
    assert llm.available(), "needs ANTHROPIC_API_KEY"

    print(f"=== live case: {REPO}/issues/38 (real repo, real branch) ===")
    source = prepare_source()
    print(f"workspace source assembled: real app/ package + acceptance test")

    run_id = f"live-swe-{uuid.uuid4().hex[:8]}"
    rt = Runtime()
    result = rt.run(build_graph(run_id, source=source), {"issue": ISSUE}, run_id)

    pause = result["__interrupt__"][0].value
    print(f"\npaused: {pause['question']}")
    print(f"review: {pause['review'][:400]}")

    final = rt.resume(build_graph(run_id, source=source), run_id,
                      decision={"approved": True, "by": "maintainer-gate@local"})
    print(f"\noutcome: {final['response']}")

    print("\n--- the patch a maintainer could apply ---")
    patch = Path(final["workspace"]) / "change.patch"
    for line in patch.read_text().splitlines():
        if line.startswith(("+", "-", "@@")) and "+++" not in line and "---" not in line:
            print(line)

    with psycopg.connect(DATABASE_URL) as conn:
        print("\n--- audit trail ---")
        for e in audit.for_run(conn, run_id):
            print(f"  {e['actor']}: {e['event']}")


if __name__ == "__main__":
    main()

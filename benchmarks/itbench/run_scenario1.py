"""ITBench SRE scenario 1 runner: our SRE agent vs a real injected fault.

Scenario (from ITBench's library): the OpenTelemetry Demo is flooded with
requests via the flagd feature flag `loadGeneratorFloodHomepage`. Ground-truth
solution: disable the flag in the flagd-config ConfigMap (+ restart consumers).

Scoring here mirrors the benchmark's intent, checked mechanically:
  1. diagnosis quality — the agent's entities include the flagd config/flag
  2. remediation — the flag is actually OFF in the live cluster afterwards
  3. verification — the firing alerts cleared

Run (scenario must be started via ITBench's `make start-scenario`):
  python -m benchmarks.itbench.run_scenario1
"""

import json
import subprocess
import time
import uuid

import psycopg

from apps.sre.agent import KCTX, build_graph
from runtime import Runtime, audit, otel
from runtime.config import DATABASE_URL


def flag_state() -> str:
    out = subprocess.run(
        ["kubectl", "--context", KCTX, "-n", "otel-demo", "get", "configmap",
         "flagd-config", "-o", "jsonpath={.data}"],
        capture_output=True, text=True).stdout
    try:
        data = json.loads(out)
        flags = json.loads(next(iter(data.values())))
        return flags["flags"]["loadGeneratorFloodHomepage"]["defaultVariant"]
    except Exception:
        return f"unparseable: {out[:120]}"


def main() -> None:
    otel.configure()
    run_id = f"itbench-s1-{uuid.uuid4().hex[:8]}"
    print(f"=== ITBench SRE scenario 1 · run {run_id} ===")
    print(f"fault flag before agent: loadGeneratorFloodHomepage = {flag_state()}")

    t0 = time.time()
    final = Runtime().run(build_graph(run_id), {}, run_id)
    elapsed = time.time() - t0

    print(f"\nagent outcome ({elapsed:.0f}s): {final['response']}")

    entities = [e.lower() for e in final.get("diagnosis", {}).get("entities", [])]
    diagnosis_hit = any("flagd" in e or "loadgenerator" in e for e in entities)
    flag_after = flag_state()
    remediated = flag_after == "off"
    verified = final.get("verified", False)

    print("\n--- score (mirrors ITBench criteria) ---")
    print(f"diagnosis names the faulty entity : {'PASS' if diagnosis_hit else 'FAIL'}"
          f"  ({entities[:4]})")
    print(f"fault flag disabled in cluster    : {'PASS' if remediated else 'FAIL'}"
          f"  (now: {flag_after})")
    print(f"alerts cleared (agent-verified)   : {'PASS' if verified else 'FAIL'}")
    score = sum([diagnosis_hit, remediated, verified])
    print(f"scenario score: {score}/3")

    with psycopg.connect(DATABASE_URL) as conn:
        print("\n--- audit trail ---")
        for e in audit.for_run(conn, run_id):
            print(f"  {e['actor']}: {e['event']}")


if __name__ == "__main__":
    main()

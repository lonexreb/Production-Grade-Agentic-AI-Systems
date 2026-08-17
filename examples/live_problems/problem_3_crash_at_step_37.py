"""Live problem #3: "crashed at step 37 of 50, restarted from step 1."

Reported by real users: an agent researching 50 companies made it through 37,
burned $14 in tokens, the server restarted — and it started over from company 1,
re-spending money on work it had already done.
  - dev.to/george_belsky/your-ai-agent-crashed-at-step-47-now-what-41mb
  - klementgunndu1.hashnode.dev/your-ai-agent-just-lost-3-hours-of-work-heres-why

Below: a 50-item batch run on the runtime, hard-killed at item 37 in one
process, resumed in a fresh one. Progress lives in the checkpoint, so it
continues at 38 — every item is processed exactly once.

Run: python -m examples.live_problems.problem_3_crash_at_step_37
"""

import os
import subprocess
import sys
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from runtime import Runtime

TOTAL, CRASH_AT, COST_PER_ITEM = 50, 37, 0.30


class S(TypedDict, total=False):
    processed: list


def build_graph(run_id: str) -> StateGraph:
    def process_next(state: S) -> S:
        done = state.get("processed", [])
        item = len(done) + 1
        # (a real run would call an LLM here — ~$0.30 of tokens per item)
        if os.environ.get("OAOS_CRASH_AT") and item == int(os.environ["OAOS_CRASH_AT"]):
            print(f"[batch] 💥 server dies at item {item}", flush=True)
            os._exit(137)
        return {"processed": done + [f"company-{item}"]}

    def route(state: S) -> str:
        return "process_next" if len(state["processed"]) < TOTAL else END

    g = StateGraph(S)
    g.add_node("process_next", process_next)
    g.add_edge(START, "process_next")
    g.add_conditional_edges("process_next", route)
    return g


def main() -> None:
    if len(sys.argv) > 1:               # child mode: run/resume a specific run_id
        rid = sys.argv[1]
        final = Runtime().run(build_graph(rid), None if "--resume" in sys.argv else {},
                              rid)
        print(f"[batch] processed {len(final['processed'])}/{TOTAL}", flush=True)
        return

    rid = f"batch-{uuid.uuid4().hex[:8]}"
    print(f"=== 50-company research run {rid}: server will die at item {CRASH_AT} ===")
    p = subprocess.run([sys.executable, __file__, rid],
                       env={**os.environ, "OAOS_CRASH_AT": str(CRASH_AT)})
    assert p.returncode == 137
    wasted_naive = (CRASH_AT - 1) * COST_PER_ITEM
    print(f"process dead. a memory-only agent restarts at item 1 and re-spends "
          f"${wasted_naive:.2f} redoing {CRASH_AT - 1} items.\n")

    print("=== fresh process resumes from the checkpoint ===")
    p = subprocess.run([sys.executable, __file__, rid, "--resume"],
                       capture_output=True, text=True)
    print(p.stdout.strip())
    assert f"processed {TOTAL}/{TOTAL}" in p.stdout

    final = Runtime().history(rid)[0]["values"]
    items = final["processed"]
    assert len(items) == TOTAL and len(set(items)) == TOTAL  # each exactly once
    print(f"resumed at item {CRASH_AT}, finished all {TOTAL}. every item processed "
          f"exactly once — $0.00 re-spent (vs ${wasted_naive:.2f} without checkpoints)")
    print("PASS")


if __name__ == "__main__":
    main()

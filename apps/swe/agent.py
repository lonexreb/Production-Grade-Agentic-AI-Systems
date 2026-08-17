"""SWE Agent: issue -> plan -> code -> test -> (retry) -> review -> human merge.

The flagship app: an LLM writes real code into an isolated per-run workspace,
the runtime runs the project's real test suite against it, failures feed back
into a bounded retry loop, an LLM reviewer reads the diff, and NOTHING merges
without a human — merge is an approve-tier tool behind interrupt(), audited,
idempotent. Long-running, fully checkpointed: kill it mid-loop and it resumes.

Requires ANTHROPIC_API_KEY (runtime/llm.py). Tests skip without it; the demo
is not in CI — a coder agent without a model would be theater.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal, TypedDict

import psycopg

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from runtime import Tool, ToolRouter, audit, execute_once, llm, memory, side_effects
from runtime.config import DATABASE_URL
from runtime.tools import Approval

APP = "swe"
MAX_CODE_ATTEMPTS = 3
SAMPLE_PROJECT = Path(__file__).parent / "sample_project"
WORKSPACE_ROOT = Path(__file__).resolve().parents[2] / "workspace"


class SWEState(TypedDict, total=False):
    issue: str
    workspace: str
    plan: str
    target_file: str
    attempts: int
    tests_pass: bool
    test_output: str
    diff: str
    review: str
    approval: dict
    merge_result: dict
    response: str


def _git(workspace: str, *args: str) -> str:
    out = subprocess.run(["git", "-C", workspace, *args],
                         capture_output=True, text=True, timeout=60)
    return out.stdout.strip()


def _merge_change(workspace: str, message: str) -> dict:
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-m", message)
    sha = _git(workspace, "rev-parse", "--short", "HEAD")
    patch_file = str(Path(workspace) / "change.patch")
    Path(patch_file).write_text(_git(workspace, "show", "HEAD"))
    return {"commit": sha, "patch": patch_file}


router = ToolRouter()
router.register(Tool(name="merge_change", fn=_merge_change, risk_tier="approve"))


def make_setup_node(run_id: str, source: Path):
    def setup_node(state: SWEState) -> SWEState:
        ws = WORKSPACE_ROOT / run_id
        if not ws.exists():  # resume-safe: keep code changes from before a crash
            shutil.copytree(source, ws, ignore=shutil.ignore_patterns("__pycache__"))
            (ws / ".gitignore").write_text("__pycache__/\n")
            _git(str(ws), "init", "-q")
            _git(str(ws), "add", "-A")
            _git(str(ws), "commit", "-q", "-m", "baseline")
        return {"workspace": str(ws), "attempts": 0}

    return setup_node


def make_plan_node(run_id: str):
    def plan_node(state: SWEState) -> SWEState:
        files = [p.name for p in Path(state["workspace"]).glob("*.py")]
        plan = llm.complete(
            f"Issue: {state['issue']}\nFiles in repo: {files}\n"
            "Reply with two lines exactly:\n"
            "FILE: <the one file to modify>\n"
            "PLAN: <one sentence describing the change>",
            max_tokens=150, tier="light",
        )
        target = next((line.split(":", 1)[1].strip() for line in plan.splitlines()
                       if line.startswith("FILE:")), files[0])
        with psycopg.connect(DATABASE_URL) as conn:
            audit.ensure_schema(conn)
            audit.append(conn, run_id, "agent", "plan_made",
                         {"plan": plan, "target_file": target})
        return {"plan": plan, "target_file": target}

    return plan_node


def _strip_fences(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines) + "\n"


def make_code_node(run_id: str):
    def code_node(state: SWEState) -> SWEState:
        target = Path(state["workspace"]) / state["target_file"]
        feedback = (f"\nThe previous attempt failed these tests:\n"
                    f"{state['test_output']}\n" if state.get("test_output") else "")
        new_content = llm.complete(
            f"Issue: {state['issue']}\nPlan: {state['plan']}\n"
            f"Current content of {state['target_file']}:\n```python\n"
            f"{target.read_text()}```\n{feedback}"
            "Reply with the COMPLETE new file content, nothing else.",
            system="You are a careful software engineer. Output only code.",
            max_tokens=2000,
        )
        target.write_text(_strip_fences(new_content))
        attempts = state["attempts"] + 1
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, "agent", "code_written",
                         {"file": state["target_file"], "attempt": attempts})
        return {"attempts": attempts}

    return code_node


def make_test_node(run_id: str):
    def test_node(state: SWEState) -> SWEState:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header"],
            cwd=state["workspace"], capture_output=True, text=True, timeout=120,
        )
        passed = proc.returncode == 0
        tail = "\n".join(proc.stdout.splitlines()[-15:])
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, "agent", "tests_run",
                         {"passed": passed, "attempt": state["attempts"],
                          "output_tail": tail})
        return {"tests_pass": passed, "test_output": tail}

    return test_node


def route_after_test(state: SWEState) -> Literal["code", "review", "give_up"]:
    if state["tests_pass"]:
        return "review"
    if state["attempts"] < MAX_CODE_ATTEMPTS:
        return "code"
    return "give_up"


def make_review_node(run_id: str):
    def review_node(state: SWEState) -> SWEState:
        diff = _git(state["workspace"], "diff", "HEAD")
        review = llm.complete(
            f"Issue: {state['issue']}\nDiff:\n{diff}\n"
            "Review this change in 2-3 sentences: correctness, style, risks.",
            max_tokens=300,
        )
        with psycopg.connect(DATABASE_URL) as conn:
            audit.append(conn, run_id, "agent", "review_done", {"review": review})
        return {"diff": diff, "review": review}

    return review_node


def make_merge_gate_node(run_id: str):
    def merge_gate(state: SWEState) -> SWEState:
        decision = interrupt({
            "question": f"Merge this change? (tests pass, {state['attempts']} attempt(s))",
            "issue": state["issue"],
            "review": state["review"],
            "diff": state["diff"][:2000],
        })
        with psycopg.connect(DATABASE_URL) as conn:
            event = "approval_granted" if decision.get("approved") else "approval_rejected"
            audit.append(conn, run_id, decision.get("by", "unknown"), event, decision)
        return {"approval": decision}

    return merge_gate


def route_after_gate(state: SWEState) -> Literal["merge", "wrap_up"]:
    return "merge" if state["approval"].get("approved") else "wrap_up"


def make_merge_node(run_id: str):
    def merge_node(state: SWEState) -> SWEState:
        with psycopg.connect(DATABASE_URL) as conn:
            side_effects.ensure_schema(conn)
            result = execute_once(
                conn, side_effects.make_key(run_id, "merge"), run_id,
                lambda: router.call(
                    "merge_change", run_id=run_id,
                    approval=Approval(approved=True, by=state["approval"]["by"]),
                    workspace=state["workspace"],
                    message=f"fix: {state['issue'][:60]}",
                ),
            )
            audit.append(conn, run_id, "agent", "tool_call",
                         {"tool": "merge_change", "result": result})
        return {"merge_result": result}

    return merge_node


def make_wrap_up_node(run_id: str):
    def wrap_up(state: SWEState) -> SWEState:
        if state.get("merge_result"):
            outcome = (f"merged as {state['merge_result']['commit']} after "
                       f"{state['attempts']} attempt(s); patch at "
                       f"{state['merge_result']['patch']}")
            ok = True
        elif not state.get("tests_pass"):
            outcome = (f"gave up after {state['attempts']} attempts — tests still "
                       "failing; escalating to a human engineer")
            ok = False
        else:
            outcome = "merge rejected by reviewer"
            ok = False
        with psycopg.connect(DATABASE_URL) as conn:
            memory.ensure_schema(conn)
            memory.write_episode(conn, APP, run_id,
                                 f"issue '{state['issue'][:60]}' {outcome[:80]}",
                                 {"ok": ok})
        return {"response": outcome}

    return wrap_up


def build_graph(run_id: str, source: Path = SAMPLE_PROJECT) -> StateGraph:
    g = StateGraph(SWEState)
    g.add_node("setup", make_setup_node(run_id, source))
    g.add_node("plan", make_plan_node(run_id))
    g.add_node("code", make_code_node(run_id))
    g.add_node("test", make_test_node(run_id))
    g.add_node("review", make_review_node(run_id))
    g.add_node("merge_gate", make_merge_gate_node(run_id))
    g.add_node("merge", make_merge_node(run_id))
    g.add_node("give_up", lambda s: {})
    g.add_node("wrap_up", make_wrap_up_node(run_id))
    g.add_edge(START, "setup")
    g.add_edge("setup", "plan")
    g.add_edge("plan", "code")
    g.add_edge("code", "test")
    g.add_conditional_edges("test", route_after_test)
    g.add_edge("review", "merge_gate")
    g.add_conditional_edges("merge_gate", route_after_gate)
    g.add_edge("merge", "wrap_up")
    g.add_edge("give_up", "wrap_up")
    g.add_edge("wrap_up", END)
    return g

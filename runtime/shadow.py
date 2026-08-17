"""Module 7 (part 2): shadow mode — evaluate a candidate agent on recorded
traffic with side effects GUARANTEED suppressed.

ShadowRouter satisfies the ToolRouter contract but never calls a real tool fn:
every call is recorded to the shadow_calls table and answered from per-tool
stub results. Approval enforcement still applies — a shadow run that would
violate a gate fails in shadow, which is the point.

shadowed(module, stubs) swaps an app module's `router` for the shadow double
(convention: every app exposes a module-level `router`). Shadow runs use a
'shadow-' run_id prefix; their checkpoints/audit rows are namespaced there.

compare() answers the operator's actual question: if we deploy the candidate,
which recorded cases change outcome, and what would it have done differently?
"""

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import psycopg

from runtime.config import DATABASE_URL
from runtime.tools import Approval, ApprovalRequired, ToolError, ToolRouter

DDL = """
CREATE TABLE IF NOT EXISTS shadow_calls (
    id         bigserial PRIMARY KEY,
    run_id     text NOT NULL,
    tool       text NOT NULL,
    kwargs     jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


@dataclass
class ShadowRouter:
    """A router double: records intent, returns stubs, never touches the world."""

    inner: ToolRouter
    stubs: dict[str, Any] = field(default_factory=dict)

    def call(self, name: str, run_id: str = "", approval: Approval | None = None,
             **kwargs: Any) -> Any:
        tool = self.inner.tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool: {name}")
        if tool.risk_tier == "approve" and not (approval and approval.approved):
            raise ApprovalRequired(f"{name} is approve-tier (shadow)")
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(DDL)
            conn.execute(
                "INSERT INTO shadow_calls (run_id, tool, kwargs) VALUES (%s, %s, %s)",
                (run_id, name, json.dumps(kwargs, default=str)),
            )
            conn.commit()
        stub = self.stubs.get(name, {"shadow": True, "tool": name})
        return stub(**kwargs) if callable(stub) else stub


@contextmanager
def shadowed(app_module, stubs: dict[str, Any]):
    """Swap `app_module.router` for a ShadowRouter for the duration."""
    real = app_module.router
    app_module.router = ShadowRouter(inner=real, stubs=stubs)
    try:
        yield
    finally:
        app_module.router = real


def calls_for(run_id: str) -> list[dict]:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(DDL)
        conn.commit()
        rows = conn.execute(
            "SELECT tool, kwargs FROM shadow_calls WHERE run_id = %s ORDER BY id",
            (run_id,),
        ).fetchall()
    return [{"tool": t, "kwargs": k} for t, k in rows]


def compare(baseline: dict, candidate: dict) -> dict:
    """Diff two shadow observations of the same case: {changed, deltas}."""
    deltas = {
        key: {"baseline": baseline.get(key), "candidate": candidate.get(key)}
        for key in set(baseline) | set(candidate)
        if baseline.get(key) != candidate.get(key)
    }
    return {"changed": bool(deltas), "deltas": deltas}

"""Module 5 (part 2): approval API — answer a paused run over HTTP.

create_app() is parameterized with the app's graph builder so the runtime stays
app-agnostic. Serve it per app, e.g.:  python -m apps.hr.api

# ponytail: single-app factory; a run_id -> app registry lands when a second
# app needs to share one API process.
"""

from typing import Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from runtime.engine import Runtime


class Decision(BaseModel):
    by: str
    note: str = ""


def create_app(build_graph: Callable, runtime: Runtime | None = None) -> FastAPI:
    rt = runtime or Runtime()
    app = FastAPI(title="OpenAgentOS approval API")

    def _paused_or_404(run_id: str) -> None:
        status = rt.status(run_id)
        if status is None:
            raise HTTPException(404, f"unknown run: {run_id}")
        if status != "paused":
            raise HTTPException(409, f"run is {status}, not awaiting approval")

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        status = rt.status(run_id)
        if status is None:
            raise HTTPException(404, f"unknown run: {run_id}")
        body = {"run_id": run_id, "status": status}
        if status == "paused":
            body["pending"] = rt.pending(build_graph(run_id), run_id)
        return body

    @app.post("/runs/{run_id}/approve")
    def approve(run_id: str, decision: Decision) -> dict:
        _paused_or_404(run_id)
        final = rt.resume(build_graph(run_id), run_id,
                          decision={"approved": True, "by": decision.by,
                                    "note": decision.note})
        return {"run_id": run_id, "status": rt.status(run_id),
                "response": final.get("response")}

    @app.post("/runs/{run_id}/reject")
    def reject(run_id: str, decision: Decision) -> dict:
        _paused_or_404(run_id)
        final = rt.resume(build_graph(run_id), run_id,
                          decision={"approved": False, "by": decision.by,
                                    "note": decision.note})
        return {"run_id": run_id, "status": rt.status(run_id),
                "response": final.get("response")}

    return app

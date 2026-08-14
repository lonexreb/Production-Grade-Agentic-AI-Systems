"""Approval API: a paused run is inspectable and answerable over HTTP."""

import uuid

from fastapi.testclient import TestClient

from apps.hr import agent as hr
from runtime import Runtime
from runtime.api import create_app

EMAIL = {"email": "please update my direct deposit"}


def _paused_run() -> str:
    run_id = f"api-{uuid.uuid4().hex[:8]}"
    Runtime().run(
        hr.build_graph(run_id),
        {**EMAIL, "employee": f"{run_id}@corp.example"},
        run_id,
    )
    return run_id


client = TestClient(create_app(hr.build_graph))


def test_get_paused_run_shows_pending_question():
    run_id = _paused_run()
    body = client.get(f"/runs/{run_id}").json()
    assert body["status"] == "paused"
    assert "Approve update_direct_deposit" in body["pending"]["question"]


def test_approve_over_http_completes_run():
    run_id = _paused_run()
    r = client.post(f"/runs/{run_id}/approve", json={"by": "mgr@corp.example"})
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert "completed" in r.json()["response"]

    # answering the same run again is a conflict, not a double execution
    r2 = client.post(f"/runs/{run_id}/approve", json={"by": "mgr@corp.example"})
    assert r2.status_code == 409


def test_reject_over_http():
    run_id = _paused_run()
    r = client.post(f"/runs/{run_id}/reject",
                    json={"by": "mgr@corp.example", "note": "unverified bank"})
    assert r.status_code == 200
    assert "declined" in r.json()["response"]


def test_unknown_run_404():
    assert client.get("/runs/nope").status_code == 404

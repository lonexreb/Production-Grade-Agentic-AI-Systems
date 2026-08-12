"""Tool router: retries transient failures, gives up after the budget, enforces timeout."""

import pytest

from runtime.tools import Tool, ToolError, ToolRouter


def test_retries_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("blip")
        return "ok"

    r = ToolRouter()
    r.register(Tool(name="flaky", fn=flaky, max_retries=3))
    assert r.call("flaky") == "ok"
    assert len(calls) == 3


def test_exhausted_budget_raises():
    r = ToolRouter()
    r.register(Tool(name="dead", fn=lambda: 1 / 0, max_retries=1))
    with pytest.raises(ToolError, match="failed after 2 attempts"):
        r.call("dead")


def test_timeout_enforced():
    import time

    r = ToolRouter()
    r.register(Tool(name="slow", fn=lambda: time.sleep(5), timeout_s=0.2, max_retries=0))
    with pytest.raises(ToolError, match="failed after 1 attempts"):
        r.call("slow")


def test_unknown_tool():
    with pytest.raises(ToolError, match="unknown tool"):
        ToolRouter().call("nope")

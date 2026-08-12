"""MCP adapter against a real server (mcp-server-time via uvx, no network/creds).

The server is pinned to mcp<2 in its own uvx env — its published release predates
the SDK 2.x rename; our runtime stays on 2.x.
"""

import json

from runtime.mcp_adapter import mcp_tool
from runtime.tools import ToolRouter

TIME_SERVER = ("uvx", ["--with", "mcp<2", "mcp-server-time"])


def test_mcp_tool_through_router():
    router = ToolRouter()
    router.register(
        mcp_tool(
            name="get_time",
            command=TIME_SERVER[0],
            args=TIME_SERVER[1],
            tool_name="get_current_time",
            timeout_s=60,
            max_retries=0,
        )
    )
    raw = router.call("get_time", timezone="America/Chicago")
    payload = json.loads(raw)
    assert payload["timezone"] == "America/Chicago"
    assert "datetime" in payload

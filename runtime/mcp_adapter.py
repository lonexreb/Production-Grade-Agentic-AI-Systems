"""Module 3 (part 2): MCP adapter — expose an MCP server's tool as a router Tool.

The returned Tool has the same manifest (timeout, retries, risk tier) as any
local tool; the router doesn't know or care that the fn speaks MCP over stdio.

# ponytail: one stdio session per call — simple and stateless, ~1s overhead.
# Keep a persistent session pool when call latency matters.
"""

import asyncio
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from runtime.tools import RiskTier, Tool


async def _call(command: str, args: list[str], tool_name: str, arguments: dict) -> Any:
    params = StdioServerParameters(command=command, args=args)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.is_error:
                raise RuntimeError(f"MCP tool {tool_name} errored: {result.content}")
            texts = [c.text for c in result.content if getattr(c, "text", None)]
            return texts[0] if len(texts) == 1 else texts


def mcp_tool(
    name: str,
    command: str,
    args: list[str],
    tool_name: str,
    timeout_s: float = 30.0,
    max_retries: int = 2,
    risk_tier: RiskTier = "auto",
) -> Tool:
    """A router Tool backed by `tool_name` on the MCP server `command args...`."""

    def fn(**arguments: Any) -> Any:
        return asyncio.run(_call(command, args, tool_name, arguments))

    return Tool(name=name, fn=fn, timeout_s=timeout_s, max_retries=max_retries,
                risk_tier=risk_tier)

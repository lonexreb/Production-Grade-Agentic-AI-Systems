"""Module 3: tool router — one gateway between agents and the outside world.

Every tool carries a manifest: timeout, retry policy, risk tier. Calls are traced.
Approve-tier tools are ENFORCED here (module 5): the router refuses to execute
them without an Approval — graphs obtain one from a human via interrupt().
"""

import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from runtime import otel

RiskTier = Literal["auto", "notify", "approve"]


@dataclass(frozen=True)
class Tool:
    name: str
    fn: Callable[..., Any]
    timeout_s: float = 30.0
    max_retries: int = 2
    risk_tier: RiskTier = "auto"
    fallback: str | None = None  # tool to try when this one exhausts its retries;
    #                              must accept the same kwargs


@dataclass(frozen=True)
class Approval:
    """A human decision authorizing one approve-tier tool call."""

    approved: bool
    by: str
    note: str = ""


class ToolError(Exception):
    """Raised after the retry budget is exhausted."""


class ApprovalRequired(Exception):
    """An approve-tier tool was called without a granting Approval."""


@dataclass
class ToolRouter:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self.tools[tool.name] = tool

    def call(
        self, name: str, run_id: str = "", approval: Approval | None = None,
        _tried: frozenset[str] = frozenset(), **kwargs: Any
    ) -> Any:
        tool = self.tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool: {name}")
        if tool.risk_tier == "approve" and not (approval and approval.approved):
            raise ApprovalRequired(
                f"{name} is approve-tier and has no granting approval"
            )

        last_err: Exception | None = None
        for attempt in range(tool.max_retries + 1):
            with otel.span(
                f"execute_tool {name}",
                **{
                    otel.ATTR_OPERATION: "execute_tool",
                    otel.ATTR_TOOL_NAME: name,
                    otel.ATTR_RUN_ID: run_id,
                    otel.ATTR_RETRY_COUNT: attempt,
                },
            ):
                try:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        return pool.submit(tool.fn, **kwargs).result(timeout=tool.timeout_s)
                except FutureTimeout as e:
                    last_err = ToolError(f"{name} timed out after {tool.timeout_s}s")
                except Exception as e:  # noqa: BLE001 - retry ladder catches all tool faults
                    last_err = e
            if attempt < tool.max_retries:
                time.sleep(min(2**attempt, 10) + random.uniform(0, 0.3))

        # ladder step: retries exhausted -> fallback tool (same kwargs contract)
        if tool.fallback and tool.fallback not in _tried:
            return self.call(tool.fallback, run_id=run_id, approval=approval,
                             _tried=_tried | {name}, **kwargs)
        raise ToolError(f"{name} failed after {tool.max_retries + 1} attempts") from last_err

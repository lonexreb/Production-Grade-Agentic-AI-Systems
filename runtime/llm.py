"""One place for LLM calls. Everything else imports complete(), nothing else
touches the anthropic SDK.

complete() returns None when ANTHROPIC_API_KEY is unset — callers must have a
deterministic fallback, which is what keeps tests and CI secret-free. Calls are
traced with token usage per the GenAI semconv attrs in runtime/otel.py.
"""

import os

from runtime import config as _config  # noqa: F401  (loads .env before the key check)
from runtime import otel

DEFAULT_MODEL = "claude-sonnet-5"


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete(prompt: str, system: str = "", model: str = DEFAULT_MODEL,
             max_tokens: int = 1024) -> str | None:
    """One-shot completion. None when no API key is configured."""
    if not available():
        return None
    import anthropic

    client = anthropic.Anthropic()
    with otel.span(
        f"llm {model}",
        **{otel.ATTR_OPERATION: "chat", "gen_ai.request.model": model},
    ) as span:
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system or anthropic.NOT_GIVEN,
            messages=[{"role": "user", "content": prompt}],
        )
        span.set_attribute("gen_ai.usage.input_tokens", msg.usage.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", msg.usage.output_tokens)
    return msg.content[0].text

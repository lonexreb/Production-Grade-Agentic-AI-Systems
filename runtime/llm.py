"""One place for LLM calls. Everything else imports complete(), nothing else
touches a model SDK.

Cost routing: callers declare a tier, not a vendor.
  tier="light" -> cheap model via OpenRouter (intent classification, one-line
                  planning); falls back to Anthropic if OpenRouter is missing
                  or errors — the retry ladder applies to model calls too.
  tier="heavy" -> Claude via Anthropic (code generation, review).

complete() returns None when no usable key exists — callers must have a
deterministic fallback, which is what keeps tests and CI secret-free. Calls are
traced with token usage per the GenAI semconv attrs in runtime/otel.py.
"""

import os

from runtime import config as _config  # noqa: F401  (loads .env before the key check)
from runtime import otel

DEFAULT_MODEL = "claude-sonnet-5"
LIGHT_MODEL = os.environ.get("OAOS_LIGHT_MODEL", "openai/gpt-4o-mini")


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENROUTER_API_KEY"))


def _anthropic(prompt: str, system: str, model: str, max_tokens: int) -> str | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
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


def _openrouter(prompt: str, system: str, model: str, max_tokens: int) -> str:
    import httpx  # already installed as an anthropic dependency

    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    with otel.span(
        f"llm {model}",
        **{otel.ATTR_OPERATION: "chat", "gen_ai.request.model": model},
    ) as span:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]},
            json={"model": model, "max_tokens": max_tokens, "messages": messages},
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()
        usage = body.get("usage", {})
        span.set_attribute("gen_ai.usage.input_tokens", usage.get("prompt_tokens", 0))
        span.set_attribute("gen_ai.usage.output_tokens", usage.get("completion_tokens", 0))
    return body["choices"][0]["message"]["content"]


def complete(prompt: str, system: str = "", model: str = DEFAULT_MODEL,
             max_tokens: int = 1024, tier: str = "heavy") -> str | None:
    """One-shot completion, routed by tier. None when no usable key exists."""
    if tier == "light" and os.environ.get("OPENROUTER_API_KEY"):
        try:
            return _openrouter(prompt, system, LIGHT_MODEL, max_tokens)
        except Exception:
            pass  # OpenRouter down/exhausted -> fall through to Anthropic
    return _anthropic(prompt, system, model, max_tokens)

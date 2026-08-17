"""Live problem #2: the retry double-charge.

Reported by real users: a payment/fulfillment call SUCCEEDS server-side but the
response times out; naive retry logic charges again. An r/AI_Agents developer's
fulfillment agent double-triggered a Printify order exactly this way; the
Stripe-timeout variant is the canonical example.
  - channel.tel/blog/idempotent-tool-calls-agent-retry-safety
  - buildmvpfast.com/blog/idempotent-ai-agent-retry-safe-patterns-production-workflow-2026

The fix: the runtime's deterministic side-effect key (run_id:node:scope) is
passed THROUGH to the provider as its idempotency key, so even
"succeeded-but-timed-out" retries dedupe server-side.

Run: python -m examples.live_problems.problem_2_retry_double_charge
"""

import uuid

from runtime import Tool, ToolRouter, side_effects
from runtime.tools import ToolError


class FakePaymentProvider:
    """Stands in for Stripe/Printify: dedupes on an idempotency key, like the
    real ones do. The cruel part: the FIRST call commits the charge, THEN the
    response is lost (timeout) — the ambiguous window that bites in production."""

    def __init__(self) -> None:
        self.charges: list[dict] = []
        self._seen_keys: set[str] = set()
        self._fail_next_response = True

    def charge(self, amount: float, idempotency_key: str | None = None) -> dict:
        if idempotency_key and idempotency_key in self._seen_keys:
            return {"status": "duplicate-suppressed", "amount": amount}
        if idempotency_key:
            self._seen_keys.add(idempotency_key)
        self.charges.append({"amount": amount})          # charge is COMMITTED...
        if self._fail_next_response:
            self._fail_next_response = False
            raise TimeoutError("response lost after commit")   # ...then the reply dies
    # ponytail: real providers persist keys ~24h; a set is the demo-sized truth
        return {"status": "charged", "amount": amount}


def main() -> None:
    print("=== the bug, reproduced (naive retry, no idempotency key) ===")
    provider = FakePaymentProvider()
    naive = ToolRouter()
    naive.register(Tool(name="pay", fn=lambda amount: provider.charge(amount),
                        max_retries=2))
    naive.call("pay", amount=49.99)   # attempt 1 commits + times out; retry charges again
    print(f"customer charged {len(provider.charges)} time(s) for ONE order"
          f"  <-- the double charge\n")
    assert len(provider.charges) == 2

    print("=== the fix (runtime side-effect key forwarded as provider key) ===")
    provider = FakePaymentProvider()
    router = ToolRouter()
    router.register(Tool(
        name="pay",
        fn=lambda amount, idempotency_key: provider.charge(amount, idempotency_key),
        max_retries=2,
    ))
    run_id = f"order-{uuid.uuid4().hex[:8]}"
    key = side_effects.make_key(run_id, "pay")   # deterministic: run:node:scope
    router.call("pay", run_id=run_id, amount=49.99, idempotency_key=key)
    print(f"customer charged {len(provider.charges)} time(s) for ONE order")
    assert len(provider.charges) == 1
    print("PASS: the retry hit the provider — and the provider deduped it")


if __name__ == "__main__":
    main()

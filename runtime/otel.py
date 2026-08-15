"""Module 6: OpenTelemetry tracing with GenAI semantic conventions.

All GenAI attribute names live HERE and nowhere else — the semconv is still
experimental upstream, so a rename must be a one-file diff (see MEMORY.md Gotchas).
"""

from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# GenAI semconv attribute names (pinned; do not inline elsewhere)
ATTR_OPERATION = "gen_ai.operation.name"   # invoke_agent | execute_tool
ATTR_AGENT_NAME = "gen_ai.agent.name"
ATTR_TOOL_NAME = "gen_ai.tool.name"
ATTR_RUN_ID = "gen_ai.conversation.id"     # closest stable id for a run/thread
ATTR_RETRY_COUNT = "openagentos.retry_count"

_configured = False


def configure(service_name: str = "openagentos") -> None:
    """Idempotent tracer setup.

    Exports OTLP/HTTP when OTEL_EXPORTER_OTLP_ENDPOINT is set (works with
    Langfuse, LangSmith, Grafana, any OTLP backend). Set OAOS_TRACE_CONSOLE=1
    to dump spans to stdout instead (debugging only — it floods demo output).
    Otherwise spans are recorded but not exported.
    """
    import os

    global _configured
    if _configured:
        return
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter()  # reads endpoint/headers from standard OTEL_* env
    elif os.environ.get("OAOS_TRACE_CONSOLE"):
        exporter = ConsoleSpanExporter()
    else:
        exporter = None
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True


def tracer() -> trace.Tracer:
    return trace.get_tracer("openagentos")


@contextmanager
def span(name: str, **attributes):
    with tracer().start_as_current_span(name) as s:
        for k, v in attributes.items():
            s.set_attribute(k, v)
        yield s

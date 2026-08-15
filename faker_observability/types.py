"""Typed data shapes shared by the catalog, the provider, and the renderers.

Field-name note for ``Span``: keys are snake_case in the Python dicts; the
``ObservabilityProvider.otlp_json()`` renderer converts them to the OTLP/JSON
encoding (lowerCamelCase keys, integer enum for ``kind``, int64 timestamps as
decimal strings, typed attribute values).
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict


AttributeValue = str | int | float | bool


class ServiceData(TypedDict):
    """One service entry in SERVICE_CORRELATIONS. All keys are required.

    kind: "http" | "grpc" | "db" | "cache" | "queue" | "worker"
    language: "python" | "java" | "javascript" | "go" | "native"
    version: semver-ish string; feeds service.version and image tags
    operations: server-side span names, OTel semantic-convention style
    dependencies: downstream catalog service names — the graph MUST stay a DAG
    latency_ms: (p50, p95) own-processing band in milliseconds
    error_types: language-appropriate exception names (subset of EXCEPTION_TYPES[language])
    """

    kind: str
    language: str
    version: str
    operations: list[str]
    dependencies: list[str]
    latency_ms: tuple[float, float]
    error_types: list[str]


class SpanEvent(TypedDict):
    time_unix_nano: int
    name: str
    attributes: dict[str, AttributeValue]


class Span(TypedDict):
    trace_id: str
    span_id: str
    parent_span_id: str
    name: str
    kind: str
    start_time_unix_nano: int
    end_time_unix_nano: int
    status_code: str
    status_message: str
    attributes: dict[str, AttributeValue]
    events: list[SpanEvent]
    resource: dict[str, str]


class TraceContext(TypedDict):
    """Accumulator threaded through the ``trace()`` materialization pass.

    ``resources`` memoizes one resource-attribute dict per service so every
    span of that service in the trace shares the same identity.
    """

    trace_id: str
    spans: list[Span]
    resources: dict[str, dict[str, str]]


class LogRecord(TypedDict):
    """A structured application log record.

    Every field is always populated (empty string / 0 when not applicable) so
    that any ``log_line`` format can render from any record.
    """

    timestamp: datetime
    level: str
    service: str
    message: str
    trace_id: str
    span_id: str
    hostname: str
    pid: int
    client_ip: str
    http_method: str
    http_path: str
    http_status: int
    http_bytes: int


class ObservabilityScenario(TypedDict):
    trace_id: str
    traceparent: str
    spans: list[Span]
    logs: list[LogRecord]
    resources: dict[str, dict[str, str]]

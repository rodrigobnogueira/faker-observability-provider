"""ObservabilityProvider — correlated, seedable observability test data.

Determinism contract: every random draw goes through the Faker generator's
seeded RNG (``self.generator.random`` or ``self.random_*`` helpers). The
global ``random``/``uuid``/``secrets`` modules are never used, so
``Faker.seed()`` / ``faker.seed_instance()`` reproduce identical output.
Weighted tables are always drawn via ``_weighted`` (``use_weighting=True``)
because ``BaseProvider.__use_weighting__`` defaults to False for providers
registered with ``add_provider`` and weights would otherwise be silently
ignored.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from faker.providers import BaseProvider

from . import constants
from .types import AttributeValue, LogRecord, ObservabilityScenario, ServiceData, Span


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_SPAN_KIND_NUMBERS: dict[str, int] = {"INTERNAL": 1, "SERVER": 2, "CLIENT": 3, "PRODUCER": 4, "CONSUMER": 5}

_STANDALONE_SPAN_KINDS: dict[str, str] = {"http": "SERVER", "grpc": "SERVER", "worker": "INTERNAL", "db": "CLIENT", "cache": "CLIENT", "queue": "PRODUCER"}

_DB_SYSTEMS: dict[str, str] = {"postgres": "postgresql", "redis": "redis", "mongodb": "mongodb", "elasticsearch": "elasticsearch"}

_LOG_FORMATS: tuple[str, ...] = ("json", "access_json", "logfmt", "apache_common", "apache_combined", "apache_error", "syslog_rfc3164", "syslog_rfc5424", "nginx_error")

_APACHE_LEVELS: dict[str, str] = {"FATAL": "crit", "ERROR": "error", "WARN": "warn", "INFO": "info", "DEBUG": "debug"}

_EXCEPTION_MESSAGES: tuple[str, ...] = (
    "connection reset by peer",
    "deadline exceeded while awaiting response",
    "unexpected null value in response payload",
    "temporary failure in name resolution",
    "broken pipe while writing request body",
)

_PYTHON_SOURCE_LINES: tuple[str, ...] = (
    "response = client.send(request)",
    "row = session.execute(query).one()",
    'value = payload["order_id"]',
    "return handler(event)",
)

_CLIENT_IP_FIRST_OCTETS: tuple[int, ...] = (23, 34, 52, 64, 81, 99, 142, 177, 189, 203)


def _to_unix_nano(dt: datetime) -> int:
    """Datetime -> integer unix nanoseconds without float precision loss."""
    return ((dt - _EPOCH) // timedelta(microseconds=1)) * 1000


def _from_unix_nano(ns: int) -> datetime:
    return _EPOCH + timedelta(microseconds=ns // 1000)


class ObservabilityProvider(BaseProvider):
    """Faker provider for logs, traces, and infrastructure metadata."""

    _service_correlations: dict[str, ServiceData] | None = None

    # ------------------------------------------------------------------ #
    # Catalog access (lazy load + derived views)
    # ------------------------------------------------------------------ #

    @property
    def service_correlations(self) -> dict[str, ServiceData]:
        if ObservabilityProvider._service_correlations is None:
            from .service_correlations import SERVICE_CORRELATIONS

            ObservabilityProvider._service_correlations = SERVICE_CORRELATIONS
        return ObservabilityProvider._service_correlations

    @property
    def services(self) -> tuple[str, ...]:
        return tuple(sorted(self.service_correlations))

    @property
    def entry_services(self) -> tuple[str, ...]:
        return tuple(sorted(name for name, data in self.service_correlations.items() if data["kind"] in ("http", "grpc")))

    @property
    def all_operations(self) -> tuple[str, ...]:
        return tuple(sorted({op for data in self.service_correlations.values() for op in data["operations"]}))

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _weighted(self, table):
        return self.random_elements(table, length=1, use_weighting=True)[0]

    def _require_service(self, service: str) -> ServiceData:
        try:
            return self.service_correlations[service]
        except KeyError:
            raise ValueError(f"Unknown service {service!r}. Valid services: {', '.join(self.services)}") from None

    def _ms_to_ns(self, milliseconds: float) -> int:
        return int(milliseconds * 1_000_000)

    def _draw_processing_ns(self, latency_ms: tuple[float, float]) -> int:
        p50, p95 = latency_ms
        return self._ms_to_ns(self.generator.random.triangular(p50 * 0.5, p95 * 1.5, p50))

    def _client_ip(self) -> str:
        return "{}.{}.{}.{}".format(
            self.random_element(_CLIENT_IP_FIRST_OCTETS),
            self.random_int(0, 255),
            self.random_int(0, 255),
            self.random_int(1, 254),
        )

    def _concretize_route(self, route: str) -> str:
        return re.sub(r"\{[^}]+\}", lambda _match: str(self.random_int(1000, 999999)), route)

    # ------------------------------------------------------------------ #
    # Group 1 — IDs & trace context
    # ------------------------------------------------------------------ #

    def trace_id(self) -> str:
        return format(self.generator.random.randrange(1, 1 << 128), "032x")

    def span_id(self) -> str:
        return format(self.generator.random.randrange(1, 1 << 64), "016x")

    def traceparent(self, trace_id: str | None = None, span_id: str | None = None, sampled: bool | None = None) -> str:
        if sampled is None:
            flags = self._weighted(constants.SAMPLED_FLAGS)
        else:
            flags = "01" if sampled else "00"
        return f"00-{trace_id or self.trace_id()}-{span_id or self.span_id()}-{flags}"

    def tracestate(self, entries: int | None = None) -> str:
        count = self.random_int(1, 3) if entries is None else entries
        count = max(1, min(count, len(constants.TRACESTATE_VENDOR_KEYS)))
        keys = self.random_elements(constants.TRACESTATE_VENDOR_KEYS, length=count, unique=True)
        return ",".join(f"{key}={self.hexify('^' * 8)}" for key in keys)

    # ------------------------------------------------------------------ #
    # Group 2 — weighted basics
    # ------------------------------------------------------------------ #

    def log_level(self) -> str:
        return self._weighted(constants.LOG_LEVELS)

    def http_status(self) -> int:
        return self._weighted(constants.HTTP_STATUSES)

    def http_request_method(self) -> str:
        return self._weighted(constants.HTTP_METHODS)

    def error_type(self, language: str | None = None) -> str:
        if language is None:
            language = self.random_element(tuple(sorted(constants.EXCEPTION_TYPES)))
        try:
            pool = constants.EXCEPTION_TYPES[language]
        except KeyError:
            raise ValueError(f"Unknown language {language!r}. Valid languages: {', '.join(sorted(constants.EXCEPTION_TYPES))}") from None
        return self.random_element(pool)

    def log_message(self, level: str | None = None) -> str:
        level = level or self.log_level()
        try:
            pool = constants.LOG_MESSAGES[level]
        except KeyError:
            raise ValueError(f"Unknown level {level!r}. Valid levels: {', '.join(constants.LOG_MESSAGES)}") from None
        return self.random_element(pool)

    # ------------------------------------------------------------------ #
    # Group 3 — infrastructure metadata
    # ------------------------------------------------------------------ #

    def k8s_namespace(self) -> str:
        return self.random_element(constants.K8S_NAMESPACES)

    def k8s_deployment(self, service: str | None = None) -> str:
        if service is not None:
            self._require_service(service)
            return service
        return self.random_element(self.services)

    def _k8s_suffix(self, length: int) -> str:
        return "".join(self.generator.random.choice(constants.K8S_RAND_ALPHABET) for _ in range(length))

    def k8s_pod_name(self, service: str | None = None) -> str:
        deployment = self.k8s_deployment(service)
        return f"{deployment}-{self._k8s_suffix(self.random_int(9, 10))}-{self._k8s_suffix(5)}"

    def k8s_node_name(self, cloud: str | None = None) -> str:
        cloud = cloud or self.random_element(tuple(sorted(constants.CLOUD_ZONES)))
        if cloud == "aws":
            return f"ip-10-0-{self.random_int(0, 255)}-{self.random_int(1, 254)}.ec2.internal"
        if cloud == "gcp":
            return f"gke-prod-default-pool-{self.hexify('^' * 8)}-{self._k8s_suffix(4)}"
        if cloud == "azure":
            return f"aks-nodepool1-{self.numerify('########')}-vmss{self.random_int(0, 30):06d}"
        raise ValueError(f"Unknown cloud {cloud!r}. Valid clouds: {', '.join(sorted(constants.CLOUD_ZONES))}")

    def container_id(self) -> str:
        return self.hexify("^" * 64)

    def container_image(self, service: str | None = None) -> str:
        service = service or self.random_element(self.services)
        data = self._require_service(service)
        registry = self.random_element(constants.CONTAINER_REGISTRIES)
        org = self.random_element(constants.REGISTRY_ORGS)
        return f"{registry}/{org}/{service}:{data['version']}"

    def _zone_for(self, cloud: str, region: str) -> str:
        suffix = self.random_element(constants.CLOUD_ZONES[cloud][region])
        return f"{region}{suffix}" if cloud == "aws" else f"{region}-{suffix}"

    def availability_zone(self, cloud: str | None = None) -> str:
        cloud = cloud or self.random_element(tuple(sorted(constants.CLOUD_ZONES)))
        try:
            regions = constants.CLOUD_ZONES[cloud]
        except KeyError:
            raise ValueError(f"Unknown cloud {cloud!r}. Valid clouds: {', '.join(sorted(constants.CLOUD_ZONES))}") from None
        region = self.random_element(tuple(sorted(regions)))
        return self._zone_for(cloud, region)

    def resource_attributes(self, service: str | None = None) -> dict[str, str]:
        service = service or self.random_element(self.services)
        data = self._require_service(service)
        cloud = self.random_element(tuple(sorted(constants.CLOUD_ZONES)))
        region = self.random_element(tuple(sorted(constants.CLOUD_ZONES[cloud])))
        node = self.k8s_node_name(cloud)
        instance_id = "-".join(self.hexify("^" * width) for width in (8, 4, 4, 4, 12))
        return {
            "service.name": service,
            "service.version": data["version"],
            "service.instance.id": instance_id,
            "telemetry.sdk.language": constants.SDK_LANGUAGES[data["language"]],
            "k8s.namespace.name": self.k8s_namespace(),
            "k8s.pod.name": self.k8s_pod_name(service),
            "k8s.deployment.name": service,
            "k8s.node.name": node,
            "container.id": self.container_id(),
            "container.image.name": self.container_image(service),
            "host.name": node,
            "cloud.provider": cloud,
            "cloud.region": region,
            "cloud.availability_zone": self._zone_for(cloud, region),
            "deployment.environment.name": self.random_element(("production", "staging")),
        }

    # ------------------------------------------------------------------ #
    # Group 4 — catalog queries
    # ------------------------------------------------------------------ #

    def service_name(self) -> str:
        return self.random_element(self.services)

    def service_operation(self, service: str | None = None) -> str:
        service = service or self.service_name()
        return self.random_element(tuple(self._require_service(service)["operations"]))

    def service_dependencies(self, service: str) -> tuple[str, ...]:
        return tuple(self._require_service(service)["dependencies"])

    def service_language(self, service: str) -> str:
        return self._require_service(service)["language"]

    def services_by_kind(self, kind: str) -> tuple[str, ...]:
        valid_kinds = ("cache", "db", "grpc", "http", "queue", "worker")
        if kind not in valid_kinds:
            raise ValueError(f"Unknown kind {kind!r}. Valid kinds: {', '.join(valid_kinds)}")
        return tuple(sorted(name for name, data in self.service_correlations.items() if data["kind"] == kind))

    # ------------------------------------------------------------------ #
    # Group 5 — trace engine
    # ------------------------------------------------------------------ #

    def trace(
        self,
        root_service: str | None = None,
        max_depth: int = 3,
        error: bool | None = None,
        start_time: datetime | None = None,
    ) -> list[Span]:
        if not 1 <= max_depth <= 8:
            raise ValueError("max_depth must be between 1 and 8")
        root_service = self._resolve_root_service(root_service)
        if error is None:
            error = self.generator.random.random() < 0.10
        if start_time is None:
            anchor = datetime.now(timezone.utc) - timedelta(seconds=self.generator.random.uniform(0.0, 3600.0))
        elif start_time.tzinfo is None:
            anchor = start_time.replace(tzinfo=timezone.utc)
        else:
            anchor = start_time

        plan = self._plan_node(root_service, depth=1, max_depth=max_depth)
        context = {"trace_id": self.trace_id(), "spans": [], "resources": {}}
        self._materialize_node(plan, parent_span_id="", start_ns=_to_unix_nano(anchor), context=context)
        spans: list[Span] = context["spans"]
        if error:
            self._inject_error(spans)
        return spans

    def span(self, service: str | None = None) -> Span:
        service = service or self.random_element(self.entry_services)
        data = self._require_service(service)
        kind = _STANDALONE_SPAN_KINDS[data["kind"]]
        operation = self.random_element(tuple(data["operations"]))
        start_ns = _to_unix_nano(datetime.now(timezone.utc) - timedelta(seconds=self.generator.random.uniform(0.0, 3600.0)))
        end_ns = start_ns + self._draw_processing_ns(data["latency_ms"])
        name, attributes = self._span_name_and_attributes(service, data, operation, kind, is_error=False)
        return {
            "trace_id": self.trace_id(),
            "span_id": self.span_id(),
            "parent_span_id": "",
            "name": name,
            "kind": kind,
            "start_time_unix_nano": start_ns,
            "end_time_unix_nano": end_ns,
            "status_code": "UNSET",
            "status_message": "",
            "attributes": attributes,
            "events": [],
            "resource": self.resource_attributes(service),
        }

    def _resolve_root_service(self, root_service: str | None) -> str:
        if root_service is None:
            if "api-gateway" in self.service_correlations and self.generator.random.random() < 0.5:
                return "api-gateway"
            return self.random_element(self.entry_services)
        data = self._require_service(root_service)
        if data["kind"] not in ("http", "grpc"):
            raise ValueError(f"root_service must be an entry service (http/grpc); {root_service!r} has kind {data['kind']!r}")
        return root_service

    def _plan_node(self, service: str, depth: int, max_depth: int) -> dict:
        """Phase A: bottom-up duration planning for one instrumented service."""
        data = self._require_service(service)
        operation = self.random_element(tuple(data["operations"]))
        children: list[dict] = []
        dependency_names = [name for name in data["dependencies"] if self.generator.random.random() < 0.75]
        if depth == 1 and data["dependencies"] and not dependency_names:
            dependency_names = [self.random_element(tuple(data["dependencies"]))]
        for dependency in dependency_names:
            children.append(self._plan_child(dependency, depth, max_depth))

        own_ns = self._draw_processing_ns(data["latency_ms"])
        pre_ns = int(own_ns * self.generator.random.uniform(0.2, 0.5))
        tail_ns = own_ns - pre_ns
        gaps_ns = [self._ms_to_ns(self.generator.random.uniform(0.05, 0.5)) for _ in children]
        total_ns = pre_ns + sum(child["visible_ns"] + gap for child, gap in zip(children, gaps_ns)) + tail_ns
        return {
            "type": "node",
            "service": service,
            "data": data,
            "operation": operation,
            "children": children,
            "pre_ns": pre_ns,
            "gaps_ns": gaps_ns,
            "total_ns": total_ns,
        }

    def _plan_child(self, dependency: str, depth: int, max_depth: int) -> dict:
        dep_data = self._require_service(dependency)
        kind = dep_data["kind"]
        if kind in ("http", "grpc") and depth < max_depth:
            node = self._plan_node(dependency, depth=depth + 1, max_depth=max_depth)
            overhead_ns = self._ms_to_ns(self.generator.random.uniform(0.1, 2.0))
            client_ns = node["total_ns"] + 2 * overhead_ns
            return {"type": "hop", "node": node, "overhead_ns": overhead_ns, "visible_ns": client_ns}
        duration_ns = self._draw_processing_ns(dep_data["latency_ms"])
        child_type = "producer" if kind == "queue" else "leaf_client"
        operation = self.random_element(tuple(dep_data["operations"]))
        return {"type": child_type, "service": dependency, "data": dep_data, "operation": operation, "visible_ns": duration_ns}

    def _resource_for(self, service: str, context: dict) -> dict[str, str]:
        if service not in context["resources"]:
            context["resources"][service] = self.resource_attributes(service)
        return context["resources"][service]

    def _append_span(self, context: dict, service: str, kind: str, name: str, attributes: dict[str, AttributeValue], parent_span_id: str, start_ns: int, end_ns: int) -> Span:
        span: Span = {
            "trace_id": context["trace_id"],
            "span_id": self.span_id(),
            "parent_span_id": parent_span_id,
            "name": name,
            "kind": kind,
            "start_time_unix_nano": start_ns,
            "end_time_unix_nano": end_ns,
            "status_code": "UNSET",
            "status_message": "",
            "attributes": attributes,
            "events": [],
            "resource": self._resource_for(service, context),
        }
        context["spans"].append(span)
        return span

    def _materialize_node(self, plan: dict, parent_span_id: str, start_ns: int, context: dict) -> Span:
        """Phase B: top-down start-time placement; emits spans in pre-order."""
        service, data, operation = plan["service"], plan["data"], plan["operation"]
        server_kind = "SERVER" if data["kind"] in ("http", "grpc") else "INTERNAL"
        name, attributes = self._span_name_and_attributes(service, data, operation, server_kind, is_error=False)
        server_span = self._append_span(context, service, server_kind, name, attributes, parent_span_id, start_ns, start_ns + plan["total_ns"])

        cursor = start_ns + plan["pre_ns"]
        for child, gap_ns in zip(plan["children"], plan["gaps_ns"]):
            if child["type"] == "hop":
                callee = child["node"]
                client_name, client_attributes = self._client_name_and_attributes(callee["service"], callee["data"], callee["operation"])
                client_span = self._append_span(
                    context, service, "CLIENT", client_name, client_attributes, server_span["span_id"], cursor, cursor + child["visible_ns"]
                )
                callee_server = self._materialize_node(callee, parent_span_id=client_span["span_id"], start_ns=cursor + child["overhead_ns"], context=context)
                if "http.response.status_code" in client_span["attributes"] and "http.response.status_code" in callee_server["attributes"]:
                    client_span["attributes"]["http.response.status_code"] = callee_server["attributes"]["http.response.status_code"]
            else:
                kind = "PRODUCER" if child["type"] == "producer" else "CLIENT"
                if child["data"]["kind"] in ("http", "grpc"):
                    leaf_name, leaf_attributes = self._client_name_and_attributes(child["service"], child["data"], child["operation"])
                else:
                    leaf_name, leaf_attributes = self._span_name_and_attributes(child["service"], child["data"], child["operation"], kind, is_error=False)
                self._append_span(context, service, kind, leaf_name, leaf_attributes, server_span["span_id"], cursor, cursor + child["visible_ns"])
            cursor += child["visible_ns"] + gap_ns
        return server_span

    def _span_name_and_attributes(self, service: str, data: ServiceData, operation: str, kind: str, is_error: bool) -> tuple[str, dict[str, AttributeValue]]:
        service_kind = data["kind"]
        if service_kind == "http":
            method, _, route = operation.partition(" ")
            status = 200 if method != "POST" else self.random_element((200, 201))
            attributes: dict[str, AttributeValue] = {
                "http.request.method": method,
                "http.route": route,
                "url.path": self._concretize_route(route),
                "url.scheme": "https",
                "http.response.status_code": status,
                "client.address": self._client_ip(),
                "network.protocol.version": "1.1",
            }
            return operation, attributes
        if service_kind == "grpc":
            _, _, remainder = operation.partition("/")
            rpc_service, _, rpc_method = remainder.partition("/")
            return operation, {"rpc.system": "grpc", "rpc.service": rpc_service, "rpc.method": rpc_method, "rpc.grpc.status_code": 0}
        if service_kind in ("db", "cache"):
            return operation, self._db_attributes(service, operation)
        if service_kind == "queue":
            _, _, destination = operation.partition(" ")
            return operation, {"messaging.system": "kafka", "messaging.destination.name": destination, "messaging.operation.type": "send", "server.address": service}
        return operation, {}

    def _client_name_and_attributes(self, callee: str, callee_data: ServiceData, operation: str) -> tuple[str, dict[str, AttributeValue]]:
        if callee_data["kind"] == "http":
            method, _, route = operation.partition(" ")
            status = 200 if method != "POST" else self.random_element((200, 201))
            attributes: dict[str, AttributeValue] = {
                "http.request.method": method,
                "url.full": f"https://{callee}:8080{self._concretize_route(route)}",
                "http.response.status_code": status,
                "server.address": callee,
            }
            return method, attributes
        # gRPC client spans keep the full method name and the same attributes.
        _, _, remainder = operation.partition("/")
        rpc_service, _, rpc_method = remainder.partition("/")
        return operation, {"rpc.system": "grpc", "rpc.service": rpc_service, "rpc.method": rpc_method, "rpc.grpc.status_code": 0, "server.address": callee}

    def _db_attributes(self, service: str, operation: str) -> dict[str, AttributeValue]:
        attributes: dict[str, AttributeValue] = {"db.system.name": _DB_SYSTEMS[service], "server.address": service}
        if service == "redis":
            attributes["db.operation.name"] = operation
            return attributes
        op_name, _, target = operation.partition(" ")
        attributes["db.operation.name"] = op_name
        if "." in target:
            namespace, _, collection = target.partition(".")
            attributes["db.namespace"] = namespace
            attributes["db.collection.name"] = collection
        elif target:
            attributes["db.collection.name"] = target
        if service == "postgres" and target:
            table = target.partition(".")[2] or target
            attributes["db.query.text"] = f"{op_name} * FROM {table} WHERE id = $1" if op_name == "SELECT" else f"{op_name} {table} ..."
        return attributes

    def _inject_error(self, spans: list[Span]) -> None:
        children_of: dict[str, list[Span]] = {}
        by_id: dict[str, Span] = {span["span_id"]: span for span in spans}
        for span in spans:
            children_of.setdefault(span["parent_span_id"], []).append(span)
        leaves = [span for span in spans if span["span_id"] not in {s["parent_span_id"] for s in spans}]
        origin = self.random_element(tuple(leaves))

        owner = self.service_correlations[origin["resource"]["service.name"]]
        owner_language = owner["language"]
        exception_type = self.random_element(tuple(owner["error_types"]))
        exception_message = self.random_element(_EXCEPTION_MESSAGES)
        origin_duration = origin["end_time_unix_nano"] - origin["start_time_unix_nano"]
        origin["events"].append(
            {
                "time_unix_nano": origin["start_time_unix_nano"] + (origin_duration * 4) // 5,
                "name": "exception",
                "attributes": {
                    "exception.type": exception_type,
                    "exception.message": exception_message,
                    "exception.stacktrace": self.stacktrace(language=owner_language, exception=exception_type),
                },
            }
        )
        http_error_code = self.random_element(constants.HTTP_5XX)
        grpc_error_code = self.random_element(constants.GRPC_ERROR_CODES)

        span_on_path: Span | None = origin
        while span_on_path is not None:
            span_on_path["status_code"] = "ERROR"
            span_on_path["status_message"] = f"{exception_type}: {exception_message}" if span_on_path is origin else f"downstream failure: {exception_type}"
            if "http.response.status_code" in span_on_path["attributes"]:
                span_on_path["attributes"]["http.response.status_code"] = http_error_code
            if "rpc.grpc.status_code" in span_on_path["attributes"]:
                span_on_path["attributes"]["rpc.grpc.status_code"] = grpc_error_code
            span_on_path = by_id.get(span_on_path["parent_span_id"])

    def otlp_json(self, spans: list[Span] | None = None) -> dict:
        from . import __version__

        if spans is None:
            spans = self.trace()
        grouped: dict[str, list[Span]] = {}
        resources: dict[str, dict[str, str]] = {}
        for span in spans:
            service = span["resource"]["service.name"]
            grouped.setdefault(service, []).append(span)
            resources.setdefault(service, span["resource"])
        resource_spans = []
        for service, service_spans in grouped.items():
            resource_spans.append(
                {
                    "resource": {"attributes": self._otlp_attributes(resources[service])},
                    "scopeSpans": [
                        {
                            "scope": {"name": "faker-observability", "version": __version__},
                            "spans": [self._otlp_span(span) for span in service_spans],
                        }
                    ],
                }
            )
        return {"resourceSpans": resource_spans}

    def _otlp_attributes(self, attributes: dict[str, AttributeValue]) -> list[dict]:
        encoded = []
        for key, value in attributes.items():
            if isinstance(value, bool):
                typed: dict[str, AttributeValue] = {"boolValue": value}
            elif isinstance(value, int):
                typed = {"intValue": str(value)}
            elif isinstance(value, float):
                typed = {"doubleValue": value}
            else:
                typed = {"stringValue": value}
            encoded.append({"key": key, "value": typed})
        return encoded

    def _otlp_span(self, span: Span) -> dict:
        encoded: dict = {
            "traceId": span["trace_id"],
            "spanId": span["span_id"],
            "name": span["name"],
            "kind": _SPAN_KIND_NUMBERS[span["kind"]],
            "startTimeUnixNano": str(span["start_time_unix_nano"]),
            "endTimeUnixNano": str(span["end_time_unix_nano"]),
            "attributes": self._otlp_attributes(span["attributes"]),
            "status": {"code": 2, "message": span["status_message"]} if span["status_code"] == "ERROR" else {},
        }
        if span["parent_span_id"]:
            encoded["parentSpanId"] = span["parent_span_id"]
        if span["events"]:
            encoded["events"] = [
                {"timeUnixNano": str(event["time_unix_nano"]), "name": event["name"], "attributes": self._otlp_attributes(event["attributes"])}
                for event in span["events"]
            ]
        return encoded

    # ------------------------------------------------------------------ #
    # Stacktraces
    # ------------------------------------------------------------------ #

    def stacktrace(self, language: str = "python", exception: str | None = None) -> str:
        renderers = {
            "python": self._stacktrace_python,
            "java": self._stacktrace_java,
            "javascript": self._stacktrace_javascript,
            "go": self._stacktrace_go,
        }
        try:
            renderer = renderers[language]
        except KeyError:
            raise ValueError(f"Unknown language {language!r}. Valid languages: {', '.join(sorted(renderers))}") from None
        exception = exception or self.error_type(language)
        return renderer(exception)

    def _stacktrace_python(self, exception: str) -> str:
        lines = ["Traceback (most recent call last):"]
        frames = list(self.random_elements(constants.PYTHON_APP_FRAMES, length=self.random_int(2, 3), unique=True))
        frames += list(self.random_elements(constants.PYTHON_LIB_FRAMES, length=self.random_int(1, 2), unique=True))
        for function, file_path in frames:
            lines.append(f'  File "{file_path}", line {self.random_int(10, 400)}, in {function}')
            lines.append(f"    {self.random_element(_PYTHON_SOURCE_LINES)}")
        lines.append(f"{exception}: {self.random_element(_EXCEPTION_MESSAGES)}")
        return "\n".join(lines)

    def _stacktrace_java(self, exception: str) -> str:
        lines = [f"{exception}: {self.random_element(_EXCEPTION_MESSAGES)}"]
        frames = list(self.random_elements(constants.JAVA_APP_FRAMES, length=self.random_int(2, 3), unique=True))
        frames += list(self.random_elements(constants.JAVA_FRAMEWORK_FRAMES, length=self.random_int(1, 2), unique=True))
        for method, file_name in frames:
            lines.append(f"\tat {method}({file_name}:{self.random_int(20, 900)})")
        if self.generator.random.random() < 0.20:
            cause_method, cause_file = self.random_element(constants.JAVA_FRAMEWORK_FRAMES)
            lines.append(f"Caused by: java.io.IOException: {self.random_element(_EXCEPTION_MESSAGES)}")
            lines.append(f"\tat {cause_method}({cause_file}:{self.random_int(20, 900)})")
            lines.append(f"\t... {self.random_int(3, 20)} more")
        return "\n".join(lines)

    def _stacktrace_javascript(self, exception: str) -> str:
        lines = [f"{exception}: {self.random_element(_EXCEPTION_MESSAGES)}"]
        frames = list(self.random_elements(constants.JAVASCRIPT_APP_FRAMES, length=self.random_int(1, 2), unique=True))
        frames += list(self.random_elements(constants.JAVASCRIPT_LIB_FRAMES, length=self.random_int(1, 2), unique=True))
        for function, file_path in frames:
            lines.append(f"    at {function} ({file_path}:{self.random_int(5, 300)}:{self.random_int(1, 60)})")
        return "\n".join(lines)

    def _stacktrace_go(self, exception: str) -> str:
        lines = [f"panic: {exception}", "", "goroutine 1 [running]:"]
        for function, file_path in self.random_elements(constants.GO_FRAMES, length=self.random_int(2, 4), unique=True):
            lines.append(f"{function}(0x{self.hexify('^' * 6)})")
            lines.append(f"\t{file_path}:{self.random_int(20, 600)} +0x{self.hexify('^' * 2)}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Group 6 — logs & composite scenario
    # ------------------------------------------------------------------ #

    def log_record(self, service: str | None = None, level: str | None = None, span: Span | None = None) -> LogRecord:
        if span is not None:
            return self._log_record_for_span(span, level)
        service = service or self.random_element(self.entry_services)
        self._require_service(service)
        level = level or self.log_level()
        if level not in constants.LOG_MESSAGES:
            raise ValueError(f"Unknown level {level!r}. Valid levels: {', '.join(constants.LOG_MESSAGES)}")
        timestamp = datetime.now(timezone.utc) - timedelta(seconds=self.generator.random.uniform(0.0, 3600.0))
        method, path, status, size = self._access_fields()
        return {
            "timestamp": timestamp,
            "level": level,
            "service": service,
            "message": self.log_message(level),
            "trace_id": "",
            "span_id": "",
            "hostname": self.k8s_pod_name(service),
            "pid": self.random_int(1, 32768),
            "client_ip": self._client_ip(),
            "http_method": method,
            "http_path": path,
            "http_status": status,
            "http_bytes": size,
        }

    def _log_record_for_span(self, span: Span, level: str | None) -> LogRecord:
        service = span["resource"]["service.name"]
        is_error = span["status_code"] == "ERROR"
        if is_error:
            resolved_level = "ERROR"
            message = span["status_message"] or self.log_message("ERROR")
        else:
            resolved_level = level or self.random_element(("DEBUG", "INFO", "INFO", "INFO", "INFO", "INFO", "INFO", "WARN"))
            message = self.log_message(resolved_level)
        duration = span["end_time_unix_nano"] - span["start_time_unix_nano"]
        timestamp_ns = span["start_time_unix_nano"] + (self.generator.random.randrange(duration) if duration > 0 else 0)
        attributes = span["attributes"]
        if "http.request.method" in attributes:
            method = str(attributes["http.request.method"])
            path = str(attributes.get("url.path") or attributes.get("url.full", "/"))
            status = int(attributes.get("http.response.status_code", 200))
            size = 0 if status in (204, 304) else self.random_int(200, 20000)
        else:
            method, path, status, size = self._access_fields()
            if is_error:
                status = self.random_element(constants.HTTP_5XX)
        return {
            "timestamp": _from_unix_nano(timestamp_ns),
            "level": resolved_level,
            "service": service,
            "message": message,
            "trace_id": span["trace_id"],
            "span_id": span["span_id"],
            "hostname": span["resource"]["k8s.pod.name"],
            "pid": self.random_int(1, 32768),
            "client_ip": str(attributes.get("client.address", self._client_ip())),
            "http_method": method,
            "http_path": path,
            "http_status": status,
            "http_bytes": size,
        }

    def _access_fields(self) -> tuple[str, str, int, int]:
        roll = self.generator.random.random()
        if roll < 0.08:
            return "GET", self.random_element(constants.PROBE_PATHS), 200, self.random_int(20, 400)
        if roll < 0.30:
            status = self.random_element((200, 200, 200, 304))
            return "GET", self.random_element(constants.STATIC_ASSET_PATHS), status, 0 if status == 304 else self.random_int(300, 80000)
        method = self.http_request_method()
        gateway_routes = tuple(self.service_correlations["api-gateway"]["operations"]) if "api-gateway" in self.service_correlations else ("GET /api/items",)
        path = self._concretize_route(self.random_element(gateway_routes).partition(" ")[2])
        status = self.http_status()
        if status in (204, 304):
            size = 0
        elif status == 404:
            size = self.random_int(150, 1500)
        elif method == "GET":
            size = self.random_int(500, 2_000_000) if self.generator.random.random() < 0.2 else self.random_int(500, 60000)
        else:
            size = self.random_int(100, 5000)
        return method, path, status, size

    def log_line(self, fmt: str = "json", record: LogRecord | None = None, service: str | None = None, level: str | None = None, span: Span | None = None) -> str:
        renderers = {
            "json": self._render_json,
            "access_json": self._render_access_json,
            "logfmt": self._render_logfmt,
            "apache_common": self._render_apache_common,
            "apache_combined": self._render_apache_combined,
            "apache_error": self._render_apache_error,
            "syslog_rfc3164": self._render_syslog_rfc3164,
            "syslog_rfc5424": self._render_syslog_rfc5424,
            "nginx_error": self._render_nginx_error,
        }
        try:
            renderer = renderers[fmt]
        except KeyError:
            raise ValueError(f"Unknown fmt {fmt!r}. Valid formats: {', '.join(_LOG_FORMATS)}") from None
        if record is None:
            record = self.log_record(service=service, level=level, span=span)
        return renderer(record)

    def _render_json(self, record: LogRecord) -> str:
        payload: dict[str, AttributeValue] = {
            "timestamp": record["timestamp"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record["level"].lower(),
            "service": record["service"],
            "message": record["message"],
            "hostname": record["hostname"],
            "pid": record["pid"],
        }
        if record["trace_id"]:
            payload["trace_id"] = record["trace_id"]
            payload["span_id"] = record["span_id"]
        return json.dumps(payload, separators=(",", ":"))

    def _render_access_json(self, record: LogRecord) -> str:
        payload = {
            "host": record["client_ip"],
            "user-identifier": "-",
            "datetime": record["timestamp"].strftime("%d/%b/%Y:%H:%M:%S +0000"),
            "method": record["http_method"],
            "request": record["http_path"],
            "protocol": "HTTP/1.1",
            "status": record["http_status"],
            "bytes": record["http_bytes"],
            "referer": self.random_element(constants.REFERERS),
        }
        return json.dumps(payload, separators=(",", ":"))

    def _render_logfmt(self, record: LogRecord) -> str:
        line = (
            f"time={record['timestamp'].strftime('%Y-%m-%dT%H:%M:%SZ')} level={record['level'].lower()} "
            f'service={record["service"]} msg="{record["message"]}"'
        )
        if record["trace_id"]:
            line += f" trace_id={record['trace_id']} span_id={record['span_id']}"
        return line

    def _clf_prefix(self, record: LogRecord) -> str:
        user = self.random_element(("-", "-", "-", "-", "-", "-", "-", "frank", "alice", "bob"))
        size = str(record["http_bytes"]) if record["http_bytes"] else "-"
        return (
            f"{record['client_ip']} - {user} [{record['timestamp'].strftime('%d/%b/%Y:%H:%M:%S +0000')}] "
            f'"{record["http_method"]} {record["http_path"]} HTTP/1.1" {record["http_status"]} {size}'
        )

    def _render_apache_common(self, record: LogRecord) -> str:
        return self._clf_prefix(record)

    def _render_apache_combined(self, record: LogRecord) -> str:
        if record["http_path"] in constants.PROBE_PATHS:
            user_agent = "Prometheus/2.53.0" if record["http_path"] == "/metrics" else "kube-probe/1.31"
            referer = "-"
        else:
            user_agent = self.random_element(constants.USER_AGENTS)
            referer = self.random_element(constants.REFERERS)
        return f'{self._clf_prefix(record)} "{referer}" "{user_agent}"'

    def _render_apache_error(self, record: LogRecord) -> str:
        module = self.random_element(constants.APACHE_ERROR_MODULES)
        apache_level = _APACHE_LEVELS[record["level"]]
        message = self.random_element(constants.APACHE_ERROR_MESSAGES)
        return (
            f"[{record['timestamp'].strftime('%a %b %d %H:%M:%S.%f %Y')}] [{module}:{apache_level}] "
            f"[pid {record['pid']}:tid {self.random_int(100000000000, 999999999999)}] "
            f"[client {record['client_ip']}:{self.random_int(1024, 65535)}] {message}"
        )

    def _syslog_pri(self, level: str) -> int:
        return constants.SYSLOG_FACILITY * 8 + constants.SYSLOG_SEVERITIES[level]

    def _render_syslog_rfc3164(self, record: LogRecord) -> str:
        timestamp = record["timestamp"]
        return (
            f"<{self._syslog_pri(record['level'])}>{timestamp.strftime('%b')} {timestamp.day:2d} "
            f"{timestamp.strftime('%H:%M:%S')} {record['hostname']} {record['service']}[{record['pid']}]: {record['message']}"
        )

    def _render_syslog_rfc5424(self, record: LogRecord) -> str:
        timestamp = record["timestamp"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if record["trace_id"]:
            structured_data = f'[trace@32473 trace_id="{record["trace_id"]}" span_id="{record["span_id"]}"]'
        else:
            structured_data = "-"
        return (
            f"<{self._syslog_pri(record['level'])}>1 {timestamp} {record['hostname']} "
            f"{record['service']} {record['pid']} - {structured_data} {record['message']}"
        )

    def _render_nginx_error(self, record: LogRecord) -> str:
        nginx_level = _APACHE_LEVELS[record["level"]]
        message = self.random_element(constants.NGINX_ERROR_MESSAGES)
        return (
            f"{record['timestamp'].strftime('%Y/%m/%d %H:%M:%S')} [{nginx_level}] {record['pid']}#0: "
            f"*{self.random_int(1, 99999)} {message}, client: {record['client_ip']}, server: {record['service']}, "
            f'request: "{record["http_method"]} {record["http_path"]} HTTP/1.1", host: "{record["service"]}"'
        )

    def observability_scenario(self, root_service: str | None = None, error: bool | None = None, start_time: datetime | None = None) -> ObservabilityScenario:
        spans = self.trace(root_service=root_service, error=error, start_time=start_time)
        root = spans[0]
        logs = [self.log_record(span=span) for span in spans]
        resources: dict[str, dict[str, str]] = {}
        for span in spans:
            resources.setdefault(span["resource"]["service.name"], span["resource"])
        return {
            "trace_id": root["trace_id"],
            "traceparent": f"00-{root['trace_id']}-{root['span_id']}-01",
            "spans": spans,
            "logs": logs,
            "resources": resources,
        }

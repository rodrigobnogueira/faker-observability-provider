"""Trace engine invariants, error propagation, and OTLP/JSON encoding."""

import re

import pytest
from faker import Faker

from faker_observability import ObservabilityProvider
from faker_observability.service_correlations import SERVICE_CORRELATIONS


@pytest.fixture
def faker() -> Faker:
    fake = Faker()
    fake.add_provider(ObservabilityProvider)
    return fake


HEX_ID_RE = re.compile(r"^[0-9a-f]+$")
VALID_KINDS = {"INTERNAL", "SERVER", "CLIENT", "PRODUCER", "CONSUMER"}
STACKTRACE_ANCHORS = {
    "python": "Traceback (most recent call last):",
    "java": "\tat ",
    "javascript": "    at ",
    "go": "goroutine 1 [running]:",
}


def sample_traces(faker: Faker) -> list[list[dict]]:
    traces = [faker.trace() for _ in range(5)]
    traces += [faker.trace(root_service="api-gateway", max_depth=4) for _ in range(3)]
    traces += [faker.trace(max_depth=1) for _ in range(2)]
    traces += [faker.trace(error=True) for _ in range(3)]
    traces += [faker.trace(root_service="inventory-service") for _ in range(2)]
    return traces


def children_of(spans: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for span in spans:
        result.setdefault(span["parent_span_id"], []).append(span)
    return result


def by_id(spans: list[dict]) -> dict[str, dict]:
    return {span["span_id"]: span for span in spans}


class TestTraceInvariants:
    def test_single_trace_id(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            assert len({span["trace_id"] for span in spans}) == 1

    def test_unique_span_ids(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            ids = [span["span_id"] for span in spans]
            assert len(ids) == len(set(ids))

    def test_single_root_and_it_is_first(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            roots = [span for span in spans if span["parent_span_id"] == ""]
            assert roots == [spans[0]]

    def test_parents_resolve_within_trace(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            known = {span["span_id"] for span in spans}
            for span in spans[1:]:
                assert span["parent_span_id"] in known

    def test_child_time_containment(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            spans_by_id = by_id(spans)
            for span in spans[1:]:
                parent = spans_by_id[span["parent_span_id"]]
                assert span["start_time_unix_nano"] >= parent["start_time_unix_nano"]
                assert span["end_time_unix_nano"] <= parent["end_time_unix_nano"]

    def test_sequential_siblings_do_not_overlap(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            for siblings in children_of(spans).values():
                ordered = sorted(siblings, key=lambda span: span["start_time_unix_nano"])
                for earlier, later in zip(ordered, ordered[1:]):
                    assert later["start_time_unix_nano"] >= earlier["end_time_unix_nano"]

    def test_parent_duration_covers_children(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            tree = children_of(spans)
            for span in spans:
                own = span["end_time_unix_nano"] - span["start_time_unix_nano"]
                child_total = sum(child["end_time_unix_nano"] - child["start_time_unix_nano"] for child in tree.get(span["span_id"], []))
                assert own >= child_total

    def test_time_fields_are_ordered_ints(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            for span in spans:
                assert isinstance(span["start_time_unix_nano"], int)
                assert isinstance(span["end_time_unix_nano"], int)
                assert span["end_time_unix_nano"] > span["start_time_unix_nano"]

    def test_kinds_valid(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            for span in spans:
                assert span["kind"] in VALID_KINDS

    def test_client_server_pairing(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            spans_by_id = by_id(spans)
            tree = children_of(spans)
            for span in spans[1:]:
                if span["kind"] == "SERVER":
                    parent = spans_by_id[span["parent_span_id"]]
                    assert parent["kind"] == "CLIENT"
                    if "http.response.status_code" in span["attributes"] and "http.response.status_code" in parent["attributes"]:
                        assert span["attributes"]["http.response.status_code"] == parent["attributes"]["http.response.status_code"]
            for span in spans:
                if span["kind"] == "CLIENT":
                    child_spans = tree.get(span["span_id"], [])
                    assert len(child_spans) <= 1
                    for child in child_spans:
                        assert child["kind"] == "SERVER"

    def test_span_names_follow_semconv(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            spans_by_id = by_id(spans)
            for span in spans:
                attributes = span["attributes"]
                if span["kind"] == "SERVER" and "http.request.method" in attributes:
                    assert span["name"] == f"{attributes['http.request.method']} {attributes['http.route']}"
                    parent = spans_by_id.get(span["parent_span_id"])
                    if parent is not None:
                        assert parent["name"] == attributes["http.request.method"]
                if "rpc.system" in attributes:
                    assert span["name"] == f"/{attributes['rpc.service']}/{attributes['rpc.method']}"

    def test_topology_edges_exist_in_catalog(self, faker: Faker) -> None:
        for spans in sample_traces(faker):
            spans_by_id = by_id(spans)
            for span in spans[1:]:
                parent = spans_by_id[span["parent_span_id"]]
                parent_service = parent["resource"]["service.name"]
                own_service = span["resource"]["service.name"]
                if own_service != parent_service:
                    assert own_service in SERVICE_CORRELATIONS[parent_service]["dependencies"]
                if span["kind"] in ("CLIENT", "PRODUCER") and "server.address" in span["attributes"]:
                    target = span["attributes"]["server.address"]
                    assert target in SERVICE_CORRELATIONS[own_service]["dependencies"]

    def test_root_service_honored_and_validated(self, faker: Faker) -> None:
        spans = faker.trace(root_service="api-gateway")
        assert spans[0]["resource"]["service.name"] == "api-gateway"
        with pytest.raises(ValueError):
            faker.trace(root_service="postgres")
        with pytest.raises(ValueError):
            faker.trace(root_service="nope-service")
        with pytest.raises(ValueError):
            faker.trace(max_depth=0)
        with pytest.raises(ValueError):
            faker.trace(max_depth=9)

    def test_max_depth_limits_server_spans(self, faker: Faker) -> None:
        for _ in range(10):
            spans = faker.trace(root_service="api-gateway", max_depth=1)
            assert sum(1 for span in spans if span["kind"] == "SERVER") == 1


class TestErrorPropagation:
    def test_error_true_produces_error_span(self, faker: Faker) -> None:
        for _ in range(5):
            spans = faker.trace(error=True)
            assert any(span["status_code"] == "ERROR" for span in spans)

    def test_origin_exception_event(self, faker: Faker) -> None:
        for _ in range(10):
            spans = faker.trace(error=True)
            with_events = [span for span in spans if span["events"]]
            assert len(with_events) == 1
            origin = with_events[0]
            event = origin["events"][0]
            assert event["name"] == "exception"
            owner_service = origin["resource"]["service.name"]
            owner_language = SERVICE_CORRELATIONS[owner_service]["language"]
            assert event["attributes"]["exception.type"] in SERVICE_CORRELATIONS[owner_service]["error_types"]
            assert STACKTRACE_ANCHORS[owner_language] in event["attributes"]["exception.stacktrace"]
            assert origin["start_time_unix_nano"] <= event["time_unix_nano"] <= origin["end_time_unix_nano"]

    def test_ancestor_chain_is_error_with_5xx(self, faker: Faker) -> None:
        for _ in range(10):
            spans = faker.trace(error=True)
            spans_by_id = by_id(spans)
            origin = next(span for span in spans if span["events"])
            current = origin
            while current is not None:
                assert current["status_code"] == "ERROR"
                if "http.response.status_code" in current["attributes"]:
                    assert current["attributes"]["http.response.status_code"] >= 500
                if "rpc.grpc.status_code" in current["attributes"]:
                    assert current["attributes"]["rpc.grpc.status_code"] != 0
                current = spans_by_id.get(current["parent_span_id"])

    def test_off_path_spans_stay_clean(self, faker: Faker) -> None:
        for _ in range(10):
            spans = faker.trace(error=True)
            spans_by_id = by_id(spans)
            origin = next(span for span in spans if span["events"])
            on_path = set()
            current = origin
            while current is not None:
                on_path.add(current["span_id"])
                current = spans_by_id.get(current["parent_span_id"])
            for span in spans:
                if span["span_id"] not in on_path:
                    assert span["status_code"] == "UNSET"
                    if "http.response.status_code" in span["attributes"]:
                        assert span["attributes"]["http.response.status_code"] < 500

    def test_error_false_is_clean(self, faker: Faker) -> None:
        for _ in range(10):
            spans = faker.trace(error=False)
            assert all(span["status_code"] == "UNSET" for span in spans)
            assert all(not span["events"] for span in spans)

    def test_error_status_messages_nonempty(self, faker: Faker) -> None:
        for _ in range(5):
            spans = faker.trace(error=True)
            for span in spans:
                if span["status_code"] == "ERROR":
                    assert span["status_message"]


class TestOtlpJson:
    def test_top_level_shape_and_grouping(self, faker: Faker) -> None:
        spans = faker.trace(root_service="api-gateway", max_depth=3)
        document = faker.otlp_json(spans)
        assert set(document) == {"resourceSpans"}
        services = {span["resource"]["service.name"] for span in spans}
        assert len(document["resourceSpans"]) == len(services)

    def test_envelope_keys(self, faker: Faker) -> None:
        document = faker.otlp_json(faker.trace())
        for resource_span in document["resourceSpans"]:
            assert set(resource_span) == {"resource", "scopeSpans"}
            assert set(resource_span["resource"]) == {"attributes"}
            for scope_span in resource_span["scopeSpans"]:
                assert scope_span["scope"]["name"] == "faker-observability"
                assert scope_span["spans"]

    def test_kind_is_integer_enum(self, faker: Faker) -> None:
        document = faker.otlp_json(faker.trace())
        for resource_span in document["resourceSpans"]:
            for span in resource_span["scopeSpans"][0]["spans"]:
                assert isinstance(span["kind"], int)
                assert 1 <= span["kind"] <= 5

    def test_timestamps_are_decimal_strings(self, faker: Faker) -> None:
        document = faker.otlp_json(faker.trace())
        for resource_span in document["resourceSpans"]:
            for span in resource_span["scopeSpans"][0]["spans"]:
                assert isinstance(span["startTimeUnixNano"], str) and span["startTimeUnixNano"].isdigit()
                assert isinstance(span["endTimeUnixNano"], str) and span["endTimeUnixNano"].isdigit()

    def test_ids_are_lowercase_hex(self, faker: Faker) -> None:
        document = faker.otlp_json(faker.trace())
        for resource_span in document["resourceSpans"]:
            for span in resource_span["scopeSpans"][0]["spans"]:
                assert HEX_ID_RE.match(span["traceId"]) and len(span["traceId"]) == 32
                assert HEX_ID_RE.match(span["spanId"]) and len(span["spanId"]) == 16

    def test_attributes_are_typed_kv_lists(self, faker: Faker) -> None:
        document = faker.otlp_json(faker.trace())
        for resource_span in document["resourceSpans"]:
            entries = resource_span["resource"]["attributes"]
            assert isinstance(entries, list)
            for entry in entries:
                assert set(entry) == {"key", "value"}
                assert len(entry["value"]) == 1
                assert next(iter(entry["value"])) in {"stringValue", "intValue", "doubleValue", "boolValue"}
            for span in resource_span["scopeSpans"][0]["spans"]:
                for attribute in span["attributes"]:
                    value_kind, value = next(iter(attribute["value"].items()))
                    if value_kind == "intValue":
                        assert isinstance(value, str)

    def test_status_encoding(self, faker: Faker) -> None:
        document = faker.otlp_json(faker.trace(error=True))
        codes = set()
        for resource_span in document["resourceSpans"]:
            for span in resource_span["scopeSpans"][0]["spans"]:
                if span["status"]:
                    assert span["status"]["code"] == 2
                    assert span["status"]["message"]
                    codes.add(2)
                else:
                    codes.add(0)
        assert 2 in codes

    def test_root_parent_omitted_and_counts_preserved(self, faker: Faker) -> None:
        spans = faker.trace()
        document = faker.otlp_json(spans)
        encoded = [span for resource_span in document["resourceSpans"] for span in resource_span["scopeSpans"][0]["spans"]]
        assert len(encoded) == len(spans)
        without_parent = [span for span in encoded if "parentSpanId" not in span]
        assert len(without_parent) == 1
        generated = faker.otlp_json()
        assert generated["resourceSpans"]

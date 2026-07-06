"""Basic provider surface: ids, weighted pools, infrastructure metadata, stacktraces."""

import re

import pytest
from faker import Faker

from faker_observability import ObservabilityProvider
from faker_observability.constants import CLOUD_ZONES, CONTAINER_REGISTRIES, EXCEPTION_TYPES, K8S_NAMESPACES, LOG_MESSAGES
from faker_observability.service_correlations import SERVICE_CORRELATIONS


@pytest.fixture
def faker() -> Faker:
    fake = Faker()
    fake.add_provider(ObservabilityProvider)
    return fake


TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
TRACEPARENT_RE = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$")
TRACESTATE_MEMBER_RE = re.compile(r"^[a-z][a-z0-9]*=[0-9a-f]{8}$")
POD_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*-[bcdfghjklmnpqrstvwxz2456789]{9,10}-[bcdfghjklmnpqrstvwxz2456789]{5}$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{64}$")
NODE_NAME_RES = {
    "aws": re.compile(r"^ip-10-0-\d{1,3}-\d{1,3}\.ec2\.internal$"),
    "gcp": re.compile(r"^gke-prod-default-pool-[0-9a-f]{8}-[bcdfghjklmnpqrstvwxz2456789]{4}$"),
    "azure": re.compile(r"^aks-nodepool1-\d{8}-vmss\d{6}$"),
}
ZONE_RES = {
    "aws": re.compile(r"^[a-z]+-[a-z]+-\d[abc]$"),
    "gcp": re.compile(r"^[a-z]+-[a-z]+\d-[a-d]$"),
    "azure": re.compile(r"^[a-z]+-[1-3]$"),
}
STACKTRACE_ANCHORS = {
    "python": "Traceback (most recent call last):",
    "java": "\tat ",
    "javascript": "    at ",
    "go": "goroutine 1 [running]:",
}


class TestIds:
    def test_trace_id_format_and_nonzero(self, faker: Faker) -> None:
        for _ in range(200):
            trace_id = faker.trace_id()
            assert TRACE_ID_RE.match(trace_id)
            assert int(trace_id, 16) != 0

    def test_span_id_format_and_nonzero(self, faker: Faker) -> None:
        for _ in range(200):
            span_id = faker.span_id()
            assert SPAN_ID_RE.match(span_id)
            assert int(span_id, 16) != 0

    def test_traceparent_format(self, faker: Faker) -> None:
        for _ in range(100):
            assert TRACEPARENT_RE.match(faker.traceparent())

    def test_traceparent_honors_explicit_parts(self, faker: Faker) -> None:
        trace_id = "0af7651916cd43dd8448eb211c80319c"
        span_id = "b7ad6b7169203331"
        assert faker.traceparent(trace_id=trace_id, span_id=span_id, sampled=True) == f"00-{trace_id}-{span_id}-01"
        assert faker.traceparent(trace_id=trace_id, span_id=span_id, sampled=False).endswith("-00")

    def test_traceparent_sampled_flag_is_weighted(self, faker: Faker) -> None:
        sampled = sum(1 for _ in range(500) if faker.traceparent().endswith("-01"))
        assert sampled > 375

    def test_tracestate_member_grammar(self, faker: Faker) -> None:
        for _ in range(50):
            members = faker.tracestate().split(",")
            assert 1 <= len(members) <= 3
            for member in members:
                assert TRACESTATE_MEMBER_RE.match(member)

    def test_tracestate_keys_unique_and_count_honored(self, faker: Faker) -> None:
        for count in (1, 2, 3, 4, 5):
            members = faker.tracestate(entries=count).split(",")
            keys = [member.split("=")[0] for member in members]
            assert len(keys) == len(set(keys))
            assert len(members) == min(count, 5)


class TestWeightedBasics:
    def test_log_level_values_and_info_dominance(self, faker: Faker) -> None:
        draws = [faker.log_level() for _ in range(500)]
        assert set(draws) <= set(LOG_MESSAGES)
        assert draws.count("INFO") > 250

    def test_http_status_values_and_2xx_majority(self, faker: Faker) -> None:
        draws = [faker.http_status() for _ in range(500)]
        assert all(isinstance(status, int) for status in draws)
        assert sum(1 for status in draws if 200 <= status < 300) > 275

    def test_http_request_method_get_dominant(self, faker: Faker) -> None:
        draws = [faker.http_request_method() for _ in range(500)]
        assert set(draws) <= {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        assert draws.count("GET") > 250

    def test_error_type_respects_language(self, faker: Faker) -> None:
        for language in ("python", "java", "javascript", "go"):
            for _ in range(20):
                assert faker.error_type(language) in EXCEPTION_TYPES[language]
        with pytest.raises(ValueError):
            faker.error_type("rust")

    def test_log_message_pools(self, faker: Faker) -> None:
        for level, pool in LOG_MESSAGES.items():
            for _ in range(10):
                assert faker.log_message(level) in pool
        with pytest.raises(ValueError):
            faker.log_message("TRACE")


class TestInfraMetadata:
    def test_k8s_namespace(self, faker: Faker) -> None:
        for _ in range(50):
            assert faker.k8s_namespace() in K8S_NAMESPACES

    def test_k8s_pod_name_format(self, faker: Faker) -> None:
        for _ in range(50):
            assert POD_NAME_RE.match(faker.k8s_pod_name())

    def test_k8s_pod_name_and_deployment_for_service(self, faker: Faker) -> None:
        assert faker.k8s_pod_name("checkout-service").startswith("checkout-service-")
        assert faker.k8s_deployment("redis") == "redis"
        assert faker.k8s_deployment() in SERVICE_CORRELATIONS
        with pytest.raises(ValueError):
            faker.k8s_pod_name("nope-service")

    def test_k8s_node_name_formats(self, faker: Faker) -> None:
        for cloud, pattern in NODE_NAME_RES.items():
            for _ in range(20):
                assert pattern.match(faker.k8s_node_name(cloud))
        assert any(pattern.match(faker.k8s_node_name()) for pattern in NODE_NAME_RES.values())
        with pytest.raises(ValueError):
            faker.k8s_node_name("ibm")

    def test_container_id(self, faker: Faker) -> None:
        for _ in range(20):
            assert CONTAINER_ID_RE.match(faker.container_id())

    def test_container_image(self, faker: Faker) -> None:
        image = faker.container_image("payment-service")
        assert image.endswith("/payment-service:5.1.0")
        assert any(image.startswith(registry + "/") for registry in CONTAINER_REGISTRIES)
        with pytest.raises(ValueError):
            faker.container_image("nope-service")

    def test_availability_zone_formats(self, faker: Faker) -> None:
        for cloud, pattern in ZONE_RES.items():
            for _ in range(20):
                assert pattern.match(faker.availability_zone(cloud))
        with pytest.raises(ValueError):
            faker.availability_zone("ibm")

    def test_resource_attributes_required_keys(self, faker: Faker) -> None:
        required = {
            "service.name",
            "service.version",
            "service.instance.id",
            "telemetry.sdk.language",
            "k8s.namespace.name",
            "k8s.pod.name",
            "k8s.deployment.name",
            "k8s.node.name",
            "container.id",
            "container.image.name",
            "host.name",
            "cloud.provider",
            "cloud.region",
            "cloud.availability_zone",
            "deployment.environment.name",
        }
        attributes = faker.resource_attributes()
        assert required <= set(attributes)

    def test_resource_attributes_internal_consistency(self, faker: Faker) -> None:
        for _ in range(20):
            attributes = faker.resource_attributes("checkout-service")
            assert attributes["service.name"] == "checkout-service"
            assert attributes["service.version"] == "4.0.2"
            assert attributes["telemetry.sdk.language"] == "java"
            assert attributes["k8s.deployment.name"] == "checkout-service"
            assert attributes["k8s.pod.name"].startswith("checkout-service-")
            assert attributes["host.name"] == attributes["k8s.node.name"]
            assert attributes["cloud.region"] in CLOUD_ZONES[attributes["cloud.provider"]]
            assert attributes["cloud.availability_zone"].startswith(attributes["cloud.region"])
            assert NODE_NAME_RES[attributes["cloud.provider"]].match(attributes["k8s.node.name"])

    def test_sdk_language_values(self, faker: Faker) -> None:
        for _ in range(30):
            assert faker.resource_attributes()["telemetry.sdk.language"] in {"python", "java", "nodejs", "go", "cpp"}


class TestStacktraces:
    def test_python_format(self, faker: Faker) -> None:
        stack = faker.stacktrace("python")
        assert stack.startswith("Traceback (most recent call last):")
        assert '  File "' in stack

    def test_java_format(self, faker: Faker) -> None:
        stack = faker.stacktrace("java")
        assert "\tat " in stack
        assert "(" in stack and ".java:" in stack

    def test_javascript_format(self, faker: Faker) -> None:
        stack = faker.stacktrace("javascript")
        assert "\n    at " in stack

    def test_go_format(self, faker: Faker) -> None:
        stack = faker.stacktrace("go")
        assert stack.startswith("panic: ")
        assert "goroutine 1 [running]:" in stack

    def test_exception_override(self, faker: Faker) -> None:
        assert "CustomBoomError" in faker.stacktrace("python", exception="CustomBoomError")
        assert faker.stacktrace("java", exception="com.acme.BoomException").startswith("com.acme.BoomException: ")

    def test_unknown_language(self, faker: Faker) -> None:
        with pytest.raises(ValueError):
            faker.stacktrace("rust")

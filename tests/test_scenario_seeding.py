"""Composite scenario coherence and seeded reproducibility."""

from datetime import datetime, timezone

import pytest
from faker import Faker

from faker_observability import ObservabilityProvider


@pytest.fixture
def faker() -> Faker:
    fake = Faker()
    fake.add_provider(ObservabilityProvider)
    return fake


def seeded(seed: int) -> Faker:
    fake = Faker()
    fake.add_provider(ObservabilityProvider)
    fake.seed_instance(seed)
    return fake


FIXED_START = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestScenario:
    def test_keys(self, faker: Faker) -> None:
        scenario = faker.observability_scenario()
        assert set(scenario) == {"trace_id", "traceparent", "spans", "logs", "resources"}
        assert scenario["traceparent"] == f"00-{scenario['trace_id']}-{scenario['spans'][0]['span_id']}-01"

    def test_logs_share_the_trace_id(self, faker: Faker) -> None:
        scenario = faker.observability_scenario()
        for log in scenario["logs"]:
            assert log["trace_id"] == scenario["trace_id"]

    def test_log_span_ids_belong_to_the_trace(self, faker: Faker) -> None:
        scenario = faker.observability_scenario()
        span_ids = {span["span_id"] for span in scenario["spans"]}
        assert len(scenario["logs"]) == len(scenario["spans"])
        for log in scenario["logs"]:
            assert log["span_id"] in span_ids

    def test_resources_match_span_resources(self, faker: Faker) -> None:
        scenario = faker.observability_scenario()
        for span in scenario["spans"]:
            service = span["resource"]["service.name"]
            assert scenario["resources"][service] == span["resource"]

    def test_error_scenario_names_the_exception(self, faker: Faker) -> None:
        scenario = faker.observability_scenario(error=True)
        origin = next(span for span in scenario["spans"] if span["events"])
        exception_type = origin["events"][0]["attributes"]["exception.type"]
        assert any(log["level"] == "ERROR" and exception_type in log["message"] for log in scenario["logs"])


class TestSeeding:
    def test_identical_traces_with_fixed_start(self) -> None:
        first = seeded(1234).trace(root_service="api-gateway", start_time=FIXED_START)
        second = seeded(1234).trace(root_service="api-gateway", start_time=FIXED_START)
        assert first == second

    def test_identical_log_lines_from_identical_spans(self) -> None:
        faker_one, faker_two = seeded(11), seeded(11)
        spans_one = faker_one.trace(start_time=FIXED_START, error=True)
        spans_two = faker_two.trace(start_time=FIXED_START, error=True)
        assert spans_one == spans_two
        line_one = faker_one.log_line(fmt="syslog_rfc5424", span=spans_one[0])
        line_two = faker_two.log_line(fmt="syslog_rfc5424", span=spans_two[0])
        assert line_one == line_two

    def test_default_start_reproduces_ids_and_structure(self) -> None:
        def shape(spans: list[dict]) -> list[tuple]:
            return [(s["trace_id"], s["span_id"], s["parent_span_id"], s["name"], s["kind"], s["status_code"]) for s in spans]

        assert shape(seeded(3).trace()) == shape(seeded(3).trace())

    def test_different_seeds_differ(self) -> None:
        assert seeded(1).trace(start_time=FIXED_START) != seeded(2).trace(start_time=FIXED_START)

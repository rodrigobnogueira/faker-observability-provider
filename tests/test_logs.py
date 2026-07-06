"""Log records, the nine line formats, and access-log plausibility couplings."""

import json
import re
from datetime import datetime, timezone

import pytest
from faker import Faker

from faker_observability import ObservabilityProvider
from faker_observability.constants import HTTP_STATUSES, PROBE_PATHS, STATIC_ASSET_PATHS
from faker_observability.service_correlations import SERVICE_CORRELATIONS


@pytest.fixture
def faker() -> Faker:
    fake = Faker()
    fake.add_provider(ObservabilityProvider)
    return fake


LOGFMT_RE = re.compile(r'^time=\S+ level=[a-z]+ service=\S+ msg=".*"( trace_id=[0-9a-f]{32} span_id=[0-9a-f]{16})?$')
APACHE_COMMON_RE = re.compile(r'^\d+\.\d+\.\d+\.\d+ - \S+ \[\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2} \+0000\] "[A-Z]+ \S+ HTTP/1\.1" \d{3} (\d+|-)$')
APACHE_COMBINED_RE = re.compile(r'^\d+\.\d+\.\d+\.\d+ - \S+ \[[^\]]+\] "[A-Z]+ \S+ HTTP/1\.1" \d{3} (\d+|-) "[^"]*" "[^"]*"$')
APACHE_ERROR_RE = re.compile(r"^\[[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2}\.\d{6} \d{4}\] \[[a-z_]+:[a-z]+\] \[pid \d+:tid \d+\] \[client \d+\.\d+\.\d+\.\d+:\d+\] .+$")
RFC5424_RE = re.compile(r"^<\d{1,3}>1 \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z \S+ \S+ \d+ - (-|\[trace@32473 [^\]]+\]) .+$")
NGINX_ERROR_RE = re.compile(r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} \[[a-z]+\] \d+#0: \*\d+ .+, client: \d+\.\d+\.\d+\.\d+, server: \S+, request: "[A-Z]+ \S+ HTTP/1\.1", host: "\S+"$')


def make_record(**overrides) -> dict:
    record = {
        "timestamp": datetime(2026, 7, 6, 2, 3, 4, 123456, tzinfo=timezone.utc),
        "level": "INFO",
        "service": "api-gateway",
        "message": "request completed successfully",
        "trace_id": "",
        "span_id": "",
        "hostname": "api-gateway-6xxtk8t8r-jff4r",
        "pid": 4242,
        "client_ip": "203.0.113.7",
        "http_method": "GET",
        "http_path": "/api/products/1",
        "http_status": 200,
        "http_bytes": 1234,
    }
    record.update(overrides)
    return record


class TestLogRecord:
    def test_fields_present_and_typed(self, faker: Faker) -> None:
        record = faker.log_record()
        assert isinstance(record["timestamp"], datetime)
        assert record["timestamp"].tzinfo is not None
        assert record["level"] in {"DEBUG", "INFO", "WARN", "ERROR", "FATAL"}
        assert record["service"] in SERVICE_CORRELATIONS
        assert record["message"]
        assert record["trace_id"] == "" and record["span_id"] == ""
        assert record["hostname"].startswith(record["service"] + "-")
        assert isinstance(record["pid"], int)
        assert isinstance(record["http_status"], int)
        assert isinstance(record["http_bytes"], int)

    def test_level_distribution_info_heavy(self, faker: Faker) -> None:
        levels = [faker.log_record()["level"] for _ in range(500)]
        assert levels.count("INFO") > 250

    def test_span_correlation(self, faker: Faker) -> None:
        error_spans = faker.trace(root_service="api-gateway", error=True)
        error_record = faker.log_record(span=error_spans[0])
        assert error_record["trace_id"] == error_spans[0]["trace_id"]
        assert error_record["span_id"] == error_spans[0]["span_id"]
        assert error_record["service"] == error_spans[0]["resource"]["service.name"]
        assert error_record["level"] == "ERROR"
        timestamp_ns = int(error_record["timestamp"].timestamp() * 1_000_000) * 1000
        assert error_spans[0]["start_time_unix_nano"] - 1000 <= timestamp_ns <= error_spans[0]["end_time_unix_nano"] + 1000

        ok_spans = faker.trace(root_service="api-gateway", error=False)
        ok_record = faker.log_record(span=ok_spans[0])
        assert ok_record["level"] in {"DEBUG", "INFO", "WARN"}
        assert ok_record["http_status"] < 500

    def test_uncorrelated_record_has_empty_trace_fields(self, faker: Faker) -> None:
        for _ in range(20):
            record = faker.log_record(service="checkout-service", level="INFO")
            assert record["trace_id"] == ""
            assert record["span_id"] == ""
            assert record["level"] == "INFO"
            assert record["service"] == "checkout-service"


class TestLogLineFormats:
    def test_json(self, faker: Faker) -> None:
        parsed = json.loads(faker.log_line(fmt="json", record=make_record()))
        assert set(parsed) == {"timestamp", "level", "service", "message", "hostname", "pid"}
        assert parsed["level"] == "info"
        correlated = json.loads(faker.log_line(fmt="json", record=make_record(trace_id="a" * 32, span_id="b" * 16)))
        assert correlated["trace_id"] == "a" * 32
        assert correlated["span_id"] == "b" * 16

    def test_access_json_flog_parity_keys(self, faker: Faker) -> None:
        parsed = json.loads(faker.log_line(fmt="access_json", record=make_record()))
        assert set(parsed) == {"host", "user-identifier", "datetime", "method", "request", "protocol", "status", "bytes", "referer"}
        assert parsed["protocol"] == "HTTP/1.1"

    def test_logfmt(self, faker: Faker) -> None:
        assert LOGFMT_RE.match(faker.log_line(fmt="logfmt", record=make_record()))
        correlated = faker.log_line(fmt="logfmt", record=make_record(trace_id="a" * 32, span_id="b" * 16))
        assert LOGFMT_RE.match(correlated)
        assert "trace_id=" in correlated

    def test_apache_common(self, faker: Faker) -> None:
        line = faker.log_line(fmt="apache_common", record=make_record())
        assert APACHE_COMMON_RE.match(line)
        zero_bytes = faker.log_line(fmt="apache_common", record=make_record(http_status=204, http_bytes=0))
        assert zero_bytes.endswith(" 204 -")

    def test_apache_combined(self, faker: Faker) -> None:
        assert APACHE_COMBINED_RE.match(faker.log_line(fmt="apache_combined", record=make_record()))
        probe = faker.log_line(fmt="apache_combined", record=make_record(http_path="/metrics"))
        assert probe.endswith('"Prometheus/2.53.0"')

    def test_apache_error(self, faker: Faker) -> None:
        assert APACHE_ERROR_RE.match(faker.log_line(fmt="apache_error", record=make_record(level="ERROR")))

    def test_syslog_rfc3164_space_padded_day(self, faker: Faker) -> None:
        line = faker.log_line(fmt="syslog_rfc3164", record=make_record())
        assert line.startswith("<134>Jul  6 02:03:04 api-gateway-6xxtk8t8r-jff4r api-gateway[4242]: ")
        padded = faker.log_line(fmt="syslog_rfc3164", record=make_record(timestamp=datetime(2026, 7, 15, 2, 3, 4, tzinfo=timezone.utc)))
        assert padded.startswith("<134>Jul 15 ")

    def test_syslog_rfc5424(self, faker: Faker) -> None:
        plain = faker.log_line(fmt="syslog_rfc5424", record=make_record())
        assert RFC5424_RE.match(plain)
        assert " - - " in plain
        correlated = faker.log_line(fmt="syslog_rfc5424", record=make_record(trace_id="a" * 32, span_id="b" * 16))
        assert RFC5424_RE.match(correlated)
        assert '[trace@32473 trace_id="' + "a" * 32 + '"' in correlated

    def test_nginx_error(self, faker: Faker) -> None:
        assert NGINX_ERROR_RE.match(faker.log_line(fmt="nginx_error", record=make_record(level="ERROR")))

    def test_unknown_format_raises(self, faker: Faker) -> None:
        with pytest.raises(ValueError, match="Valid formats"):
            faker.log_line(fmt="csv")


class TestAccessLogPlausibility:
    def test_zero_byte_statuses(self, faker: Faker) -> None:
        for _ in range(300):
            record = faker.log_record()
            if record["http_status"] in (204, 304):
                assert record["http_bytes"] == 0

    def test_write_methods_never_hit_static_or_probe_paths(self, faker: Faker) -> None:
        for _ in range(500):
            record = faker.log_record()
            if record["http_method"] != "GET":
                assert record["http_path"] not in STATIC_ASSET_PATHS
                assert record["http_path"] not in PROBE_PATHS

    def test_404_bytes_bounded(self, faker: Faker) -> None:
        for _ in range(500):
            record = faker.log_record()
            if record["http_status"] == 404:
                assert 150 <= record["http_bytes"] <= 1500

    def test_statuses_from_known_set(self, faker: Faker) -> None:
        valid = set(HTTP_STATUSES)
        for _ in range(300):
            assert faker.log_record()["http_status"] in valid

    def test_get_majority(self, faker: Faker) -> None:
        methods = [faker.log_record()["http_method"] for _ in range(500)]
        assert methods.count("GET") > 250

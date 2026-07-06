"""Showcase for faker-observability-provider.

Run with: python showcase.py
All data below is synthetic — generated for testing and demos only.
"""

import json

from faker import Faker

from faker_observability import ObservabilityProvider


fake = Faker()
fake.add_provider(ObservabilityProvider)


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subheader(title: str) -> None:
    print("\n" + "-" * 70)
    print(f"  {title}")
    print("-" * 70)


def print_span_tree(spans: list) -> None:
    children: dict = {}
    for span in spans:
        children.setdefault(span["parent_span_id"], []).append(span)

    def render(span, depth):
        duration_ms = (span["end_time_unix_nano"] - span["start_time_unix_nano"]) / 1_000_000
        error = "  ✗ ERROR" if span["status_code"] == "ERROR" else ""
        service = span["resource"]["service.name"]
        print(f"  {'  ' * depth}{service} · {span['name']} [{span['kind']}] {duration_ms:.1f}ms{error}")
        for child in children.get(span["span_id"], []):
            render(child, depth + 1)

    render(spans[0], 0)


def showcase_ids() -> None:
    print_header("W3C Trace Context")
    print(f"  trace_id:    {fake.trace_id()}")
    print(f"  span_id:     {fake.span_id()}")
    print(f"  traceparent: {fake.traceparent()}")
    print(f"  tracestate:  {fake.tracestate()}")


def showcase_weighted() -> None:
    print_header("Weighted distributions (1000 draws)")
    levels = [fake.log_level() for _ in range(1000)]
    for level in ("DEBUG", "INFO", "WARN", "ERROR", "FATAL"):
        count = levels.count(level)
        print(f"  {level:<6} {count:>4}  {'#' * (count // 20)}")


def showcase_infra() -> None:
    print_header("Kubernetes / resource metadata")
    print(f"  pod:   {fake.k8s_pod_name('checkout-service')}")
    print(f"  node:  {fake.k8s_node_name()}")
    print(f"  image: {fake.container_image('payment-service')}")
    print(f"  zone:  {fake.availability_zone()}")
    print_subheader("resource_attributes('order-service')")
    for key, value in fake.resource_attributes("order-service").items():
        print(f"  {key} = {value}")


def showcase_log_formats() -> None:
    print_header("Log line formats")
    for fmt in ("json", "access_json", "logfmt", "apache_common", "apache_combined", "apache_error", "syslog_rfc3164", "syslog_rfc5424", "nginx_error"):
        print(f"\n  [{fmt}]")
        print(f"  {fake.log_line(fmt=fmt)}")


def showcase_traces() -> None:
    print_header("Correlated trace — success")
    print_span_tree(fake.trace(root_service="api-gateway", error=False))
    print_header("Correlated trace — with error propagation")
    print_span_tree(fake.trace(root_service="api-gateway", error=True))


def showcase_otlp() -> None:
    print_header("OTLP/JSON excerpt")
    document = fake.otlp_json(fake.trace(max_depth=1))
    text = json.dumps(document, indent=2)
    print("\n".join("  " + line for line in text.splitlines()[:32]))
    print("  ...")


def showcase_stacktraces() -> None:
    print_header("Stacktraces")
    for language in ("python", "java", "javascript", "go"):
        print_subheader(language)
        print(fake.stacktrace(language))


def showcase_scenario() -> None:
    print_header("observability_scenario() — spans + correlated logs")
    scenario = fake.observability_scenario(error=True)
    print(f"  trace_id: {scenario['trace_id']}")
    print(f"  spans: {len(scenario['spans'])}, logs: {len(scenario['logs'])}, services: {len(scenario['resources'])}")
    print_subheader("correlated log lines (logfmt)")
    for log in scenario["logs"][:6]:
        print(f"  {fake.log_line(fmt='logfmt', record=log)}")


def showcase_seeding() -> None:
    print_header("Seeding — same seed, same trace")
    for seed_run in range(2):
        seeded = Faker()
        seeded.add_provider(ObservabilityProvider)
        seeded.seed_instance(1234)
        spans = seeded.trace()
        print(f"  run {seed_run + 1}: trace_id={spans[0]['trace_id']} spans={len(spans)} root={spans[0]['name']}")


def main() -> None:
    print("\n" + "=" * 70)
    print("  faker-observability-provider — showcase")
    print("  🔭 Synthetic telemetry: for testing and development only")
    print("=" * 70)
    showcase_ids()
    showcase_weighted()
    showcase_infra()
    showcase_log_formats()
    showcase_traces()
    showcase_otlp()
    showcase_stacktraces()
    showcase_scenario()
    showcase_seeding()
    print("\n" + "=" * 70)
    print("  End of Showcase")
    print("=" * 70)


if __name__ == "__main__":
    main()

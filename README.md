# faker-observability-provider

Generate **realistic, correlated, seedable observability test data**: OpenTelemetry-style trace trees, log lines in 9 formats, W3C trace contexts, Kubernetes metadata, and per-language stacktraces — as a plain [Faker](https://faker.readthedocs.io/) provider with zero extra dependencies.

Built for testing log parsers, OTel pipelines, dashboards, alert rules, and SIEM detections **inside your test suite**, where a CLI log generator can't reach.

## Installation

```bash
pip install faker-observability-provider
```

## Quick Start

```python
from faker import Faker
from faker_observability import ObservabilityProvider

fake = Faker()
fake.add_provider(ObservabilityProvider)

fake.traceparent()  # '00-7072ef7b6625afeb5efe109b815d7258-e86a5da65f5eef2f-01'
fake.log_line(fmt="logfmt")
# time=2026-07-06T03:00:38Z level=warn service=checkout-service msg="cache miss rate elevated"

spans = fake.trace(root_service="api-gateway", error=True)  # a correlated span tree
otlp = fake.otlp_json(spans)  # OTLP/JSON ResourceSpans envelope
```

💡 **Tip**: Run `python showcase.py` to see every feature end to end.

## Correlated traces (the flagship)

`trace()` generates a span tree the way a real OTel deployment emits one — **paired CLIENT/SERVER spans per hop**, timing that actually adds up, a realistic service topology, and error propagation from the failing leaf to the root:

```
api-gateway · POST /api/checkout [SERVER] 368.7ms  ✗ ERROR
  api-gateway · POST [CLIENT] 27.2ms
    auth-service · POST /auth/token [SERVER] 23.4ms
      auth-service · SELECT shop.orders [CLIENT] 3.0ms
      auth-service · GET [CLIENT] 1.1ms
  api-gateway · POST [CLIENT] 168.2ms  ✗ ERROR
    checkout-service · POST /checkout [SERVER] 167.6ms  ✗ ERROR
      checkout-service · /inventory.InventoryService/CheckStock [CLIENT] 34.4ms
        inventory-service · /inventory.InventoryService/CheckStock [SERVER] 30.9ms
      checkout-service · GET [CLIENT] 80.1ms  ✗ ERROR
        order-service · GET /orders/{id} [SERVER] 78.8ms  ✗ ERROR
          order-service · SELECT shop.orders [CLIENT] 3.0ms  ✗ ERROR
```

Guaranteed invariants (all enforced by tests):

- one `trace_id`; unique span ids; a single root span
- children are time-contained inside their parent; sequential siblings never overlap
- every HTTP/gRPC hop is a CLIENT span paired with exactly one SERVER child, status codes matching
- every edge follows the built-in 20-service topology catalog (a DAG)
- error traces have exactly one origin span with an `exception` event — type and stacktrace matching the owning service's language — and ERROR status + 5xx propagated along the root path only
- span names and attributes follow the OTel semantic conventions (`{method} {route}` server names, bare-method client names, `db.system.name`, `rpc.system`, …)

`otlp_json(spans)` renders the OTLP/JSON encoding exactly: lowerCamelCase keys, integer kind enums, int64 timestamps as decimal strings, typed attribute values.

## Seeding for reproducibility

Everything runs off Faker's seeded RNG — no global `random`, no `uuid4()`:

```python
fake = Faker()
fake.add_provider(ObservabilityProvider)
fake.seed_instance(1234)

fake.trace(start_time=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
# byte-identical output on every run with the same seed
```

With the default `start_time` (anchored near "now"), same-seed runs reproduce identical ids, structure, and durations; pass an explicit `start_time` for byte-identical fixtures.

## Log formats (9)

```text
json            {"timestamp":"2026-07-06T03:00:38.858Z","level":"info","service":"checkout-service","message":"scheduled task finished","hostname":"checkout-service-bqzx2gc22n-sp4pz","pid":20723,"trace_id":"5815…","span_id":"c4cf…"}
access_json     {"host":"34.220.137.252","user-identifier":"-","datetime":"06/Jul/2026:02:55:52 +0000","method":"GET","request":"/api/checkout","protocol":"HTTP/1.1","status":200,"bytes":59441,"referer":"https://shop.example.com/"}
logfmt          time=2026-07-06T03:00:38Z level=warn service=checkout-service msg="cache miss rate elevated" trace_id=5815… span_id=c4cf…
apache_common   189.109.195.200 - - [06/Jul/2026:02:20:35 +0000] "GET /favicon.ico HTTP/1.1" 304 -
apache_combined 99.242.10.190 - frank [06/Jul/2026:02:15:40 +0000] "GET /static/app.css HTTP/1.1" 200 19338 "https://shop.example.com/products" "python-requests/2.32.0"
apache_error    [Mon Jul 06 02:42:38.621209 2026] [core:info] [pid 7509:tid 727028976795] [client 203.7.80.223:45947] AH02032: Hostname provided via SNI and hostname provided via HTTP have no compatible SSL setup
syslog_rfc3164  <134>Jul  6 02:28:57 inventory-service-nsvxp2nxp-5z76p inventory-service[22371]: user session created
syslog_rfc5424  <134>1 2026-07-06T03:00:38.921Z checkout-service-bqzx2gc22n-sp4pz checkout-service 22349 - [trace@32473 trace_id="5815…" span_id="c4cf…"] cache refreshed from upstream
nginx_error     2026/07/06 02:46:15 [info] 32380#0: *1557 no live upstreams while connecting to upstream, client: 34.220.199.183, server: fraud-service, request: "PUT /api/cart/547452 HTTP/1.1", host: "fraud-service"
```

Access-log fields are internally plausible: `204`/`304` render `-` bytes, write methods never hit static assets, `/healthz` and `/metrics` noise arrives with `kube-probe`/`Prometheus` user agents, and `log_line(span=...)` embeds the span's trace context (RFC 5424 carries it as spec-clean structured data under the RFC 5612 documentation enterprise number).

## Available Methods

| IDs & context | Example |
|---|---|
| `trace_id()` / `span_id()` | `7072ef7b…` (32/16 hex, non-zero) |
| `traceparent()` | `00-…-…-01` (sampled flag weighted ~90%) |
| `tracestate()` | `rojo=4fd0b6f9,congo=6ea72d31` |

| Weighted basics | Example |
|---|---|
| `log_level()` | INFO-heavy distribution |
| `http_status()` / `http_request_method()` | 2xx- and GET-heavy |
| `error_type(language=…)` | `java.net.SocketTimeoutException` |
| `log_message(level=…)` | `"retrying request after transient failure (attempt 2/3)"` |

| Infrastructure | Example |
|---|---|
| `k8s_pod_name(service=…)` | `checkout-service-xtgnkbpdz-bgdjn` (real k8s suffix alphabet) |
| `k8s_node_name(cloud=…)` | `ip-10-0-12-183.ec2.internal` / GKE / AKS formats |
| `k8s_namespace()` / `k8s_deployment()` / `container_id()` / `container_image()` | — |
| `availability_zone(cloud=…)` | `us-east-1a`, `europe-west1-b`, `brazilsouth-2` |
| `resource_attributes(service=…)` | internally consistent OTel resource dict |

| Catalog queries | Example |
|---|---|
| `service_name()` / `service_operation(service=…)` | from the 20-service catalog |
| `service_dependencies(…)` / `service_language(…)` / `services_by_kind(…)` | — |

| Traces, logs & composites | Example |
|---|---|
| `trace(root_service=, max_depth=, error=, start_time=)` | correlated span tree |
| `span(service=…)` | one standalone span |
| `otlp_json(spans=…)` | OTLP/JSON envelope |
| `stacktrace(language=…, exception=…)` | format-faithful py/java/js/go |
| `log_record(service=, level=, span=)` | structured record, span-correlated |
| `log_line(fmt=, record=, span=…)` | any of the 9 formats |
| `observability_scenario(…)` | trace + correlated logs + resources |

## Why this instead of flog / telemetrygen?

| | faker-observability-provider | flog | telemetrygen |
|---|---|---|---|
| Runs inside pytest fixtures | ✅ (it's a Faker provider) | ❌ CLI binary | ❌ CLI, emits over the network |
| Correlated CLIENT/SERVER trace trees | ✅ | ❌ logs only | ❌ uncorrelated spans |
| Seedable / reproducible | ✅ | ❌ | ❌ |
| Log formats | 9 (incl. logfmt, nginx) | 7 | ❌ |
| Trace-context-correlated log lines | ✅ | ❌ | ❌ |

## Spec fidelity

Formats are implemented against: W3C Trace Context (`00` version), OpenTelemetry semantic conventions (stable HTTP/DB/exception/resource registries; experimental messaging conventions as of 2026-07), OTLP 1.x JSON encoding, RFC 5424 / RFC 3164 (including the space-padded day), Apache CLF/error-log and nginx error-log formats, and the Kubernetes name-suffix alphabet. See `AGENTS.md` for the pinned verification sources.

## Non-goals & roadmap

**Not** an OTel SDK or exporter, **not** a load generator, and it never emits over the network — it returns values. Metrics (Prometheus/OpenMetrics naming + exposition lines + OTel data points), async `CONSUMER` span continuations, `incident_scenario()`, and parallel fan-out timing are on the roadmap and will land additively.

## Disclaimer

All generated data is **synthetic test data** for development and testing only. Names, formats, and topologies mimic real systems so records look realistic, but nothing here describes any real infrastructure or real telemetry.

## Contributing

Issues and PRs are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the checks CI runs, and the determinism, trace/log and catalog rules a change has to keep.

## License

MIT

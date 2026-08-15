# AGENTS.md — faker-observability-provider

Guidance for AI agents and contributors working on this repository.
`CONTRIBUTING.md` is the human-facing distillation of this file — when a rule
here changes, update it there in the same commit.

> **SYNTHETIC DATA NOTICE:** everything this provider generates is synthetic
> test data that *mimics* real telemetry formats. It must never be presented
> as real system telemetry, and format claims must always be backed by the
> specs listed under **Verification Sources**.

## What this project is

A Python Faker provider (`faker_observability.ObservabilityProvider`) that
generates **correlated, seedable observability test data**: W3C trace
contexts, OTel-style span trees, log lines in 9 formats, Kubernetes/resource
metadata, and per-language stacktraces. The only runtime dependency is
`faker>=18.0.0`.

## Project layout

```
faker_observability/
├── __init__.py               # exports ObservabilityProvider + __version__
├── provider.py               # the provider: ids, weighted pools, infra, trace engine, renderers
├── types.py                  # TypedDict shapes (ServiceData, Span, LogRecord, ...)
├── constants.py              # flat tuples + weighted OrderedDicts + frame/message pools
└── service_correlations.py   # SERVICE_CORRELATIONS: 20-service topology catalog (DAG)
tests/                        # pytest suites (provider, catalog, trace, logs, scenario+seeding)
showcase.py                   # runnable demo of every feature
```

## Data shapes (do not drift)

`SERVICE_CORRELATIONS: dict[str, ServiceData]` — every entry has ALL keys:

```python
"payment-service": {
    "kind": "http",                       # http | grpc | db | cache | queue | worker
    "language": "java",                   # python | java | javascript | go | native
    "version": "5.1.0",                   # semver-ish; feeds service.version + image tags
    "operations": ["POST /payments"],     # OTel semconv span names (see rules below)
    "dependencies": ["fraud-service", "postgres", "kafka"],   # MUST keep the graph a DAG
    "latency_ms": (20.0, 150.0),          # (p50, p95), 0 < p50 <= p95
    "error_types": ["java.net.SocketTimeoutException", ...],  # ⊆ EXCEPTION_TYPES[language]
},
```

Derived views (`services`, `entry_services`, `all_operations`) are
**properties computed from the catalog** — never store duplicate copies.

## Correlation consistency (the core invariants)

- The dependency graph MUST remain a **DAG** (`test_dependency_graph_is_dag`).
- Span trees must satisfy: one `trace_id`; unique span ids; single root;
  child time-containment inside the parent; sequential siblings never
  overlap; every CLIENT hop pairs with exactly one SERVER child with a
  matching HTTP status; every cross-service edge exists in the catalog.
- Error injection: exactly one origin span carries the `exception` event;
  its `exception.type` comes from the **owning service's** `error_types`
  and the stacktrace matches the owner's language; all ancestors on the
  root path are ERROR with 5xx/non-zero gRPC codes; off-path spans stay
  UNSET (successful spans are UNSET, not OK — SDK-faithful).
- Span/attribute names come from the OTel semantic conventions — **copied
  exactly, never invented**: HTTP server `{method} {route}` / client bare
  `{method}`; gRPC `/{package}.{Service}/{Method}`; DB `{operation}
  {target}` (bare command for Redis); messaging `publish {destination}`.

## Determinism rules (hard requirements)

- **Never** use the global `random`, `uuid`, or `secrets` modules. Only
  `self.generator.random` and the `self.random_*` / `hexify` / `numerify`
  helpers.
- **Every weighted draw goes through `_weighted()`** which passes
  `use_weighting=True`. Rationale: `BaseProvider.__use_weighting__` defaults
  to `False` for providers registered via `add_provider()`, so a plain
  `random_element(OrderedDict)` silently ignores the weights.
- Any tuple derived from a set MUST be `sorted()` (hash randomization).
- Time math is **integer nanoseconds** (`(dt - EPOCH) // timedelta(microseconds=1) * 1000`)
  — never `dt.timestamp() * 1e9` (float64 loses precision at ns scale).
- Changing the ORDER of RNG draws inside any method is a **breaking change
  for seeded users** — call it out in release notes if unavoidable.

## Verification sources (verify against these; never invent)

- **W3C Trace Context** (Recommendation, version `00` format) — traceparent /
  tracestate grammar.
- **OpenTelemetry Semantic Conventions** — HTTP and DB conventions (stable
  registries: `http.request.method`, `http.response.status_code`,
  `url.path`, `db.system.name`, `db.namespace`, `db.operation.name`,
  `db.collection.name`, `db.query.text`); exception conventions; resource
  conventions (`service.*`, `k8s.*`, `cloud.*`, `container.*`,
  `deployment.environment.name`). Messaging conventions were still
  experimental when this was written (2026-07) — we use
  `messaging.operation.type: "send"`; re-verify before touching them.
- **OTLP JSON encoding** (OTLP 1.x): lowerCamelCase keys; `traceId`/`spanId`
  as hex strings; enums as integers (SERVER=2, CLIENT=3, ...); int64
  timestamps as **decimal strings**; attributes as `[{key, value: {…Value}}]`;
  UNSET status encodes as `{}`.
- **RFC 5424 / RFC 3164** (syslog) — including the RFC 3164 **space-padded
  day** (`Jul  6`) and PRI = facility×8 + severity. The RFC 5424 SD-ID
  `trace@32473` uses the RFC 5612 documentation enterprise number.
- **Apache** `LogFormat` (CLF `%b` renders zero bytes as `-`) and error-log
  format; **nginx** error-log format.
- **Kubernetes** apimachinery name-suffix alphabet
  (`bcdfghjklmnpqrstvwxz2456789`).
- Newer-than-training-data entities can be real — confirm against the spec
  or vendor docs; don't assume they're fake.

## Data update rules

- Catalog updates are **additive by default**: never remove or rename an
  existing service/operation unless the user asks or it is a verified
  mistake.
- Adding a service requires: DAG preserved; `error_types` drawn from the
  language pool in `constants.py`; semconv-correct operation names; tests
  still green (catalog integrity tests extend automatically).
- Update the service count in `service_correlations.py`'s docstring when it
  changes.

## Running tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy --ignore-missing-imports --no-strict-optional .
```

- **CI runs every tool the `dev` extra declares.** `tests.yml` has a lint job
  that installs `-e ".[dev]"` and runs the same arguments as
  `.pre-commit-config.yaml`. A tool that is declared but not wired into CI is
  either added to that job or dropped from the extra — no third option.

## Publishing a release

Releases are **automated via the `v*` tag → `release.yml` → PyPI Trusted
Publishing (OIDC)** pipeline. There are no tokens or secrets; PyPI trusts
the workflow directly (owner `rodrigobnogueira`, repository
`faker-observability-provider`, workflow `release.yml`, environment `pypi`).

Checklist:

1. Publish from an up-to-date `main`; check PyPI for the current latest
   version first.
2. Bump the version in **both** `pyproject.toml` and
   `faker_observability/__init__.py` (`__version__`) to the same value.
3. Run `python -m pytest`, `python -m build`, and `twine check dist/*`
   locally.
4. Commit the bump, then push a matching `vX.Y.Z` tag — the workflow tests
   (3.10 + 3.14), builds, verifies tag == pyproject version, and publishes.
5. Verify on PyPI and smoke-test a clean install
   (`pip install faker-observability-provider`).

The tag must point at a commit that already contains `release.yml`
(i.e., tag merged `main`), or the tag push won't trigger the workflow.

## Renames

A repo or package rename is not done until **every metadata surface** carries
the new name in the same change: `pyproject.toml` `[project.urls]`, README
badges and install snippets, the GitHub repo About/description, and any docs
that spell out the old name. PyPI is the one surface a commit cannot fix — it
serves the metadata of the last uploaded release — so pair the URL fix with a
patch release, or the registry keeps pointing at the old name.

# Contributing to faker-observability-provider

Thanks for helping out. This file is the human-facing distillation of
[`AGENTS.md`](AGENTS.md), which stays the source of truth for the detailed
rules (data shapes, the full verification-source list, the release
checklist) and for the extra instructions AI agents must follow. When the
two disagree, `AGENTS.md` wins — and please fix the drift in the same PR.

> **Synthetic data only.** Everything this provider generates is synthetic
> test data that *mimics* real telemetry formats. It must never be presented
> as real system telemetry, and any format claim has to be backed by one of
> the specs listed under *Verification sources* in `AGENTS.md`.

## Supported versions

- **Python 3.10 – 3.14** (`requires-python = ">=3.10"`; every version in the
  classifier list is exercised by the CI matrix).
- **Faker `>=18.0.0`** — the only runtime dependency. Adding a second runtime
  dependency is a design change: open an issue first.
- Dev tooling comes from the `dev` extra: `pytest`, `ruff`, `mypy`,
  `pre-commit`.

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install     # optional, but it runs the same tools as CI
```

## Checks you must run

These four commands are exactly what the `Tests` workflow runs (the pytest
matrix on 3.10–3.14, the lint job once), and they match the arguments in
`.pre-commit-config.yaml`:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy --ignore-missing-imports --no-strict-optional .
```

`python showcase.py` runs every feature end to end and is a quick way to eyeball
output after a change.

## Determinism rules (hard requirements)

Seeded reproducibility is the product. Breaking it is a breaking change.

- **Never** use the global `random`, `uuid`, or `secrets` modules. Draw only
  through `self.generator.random` and the `self.random_*` / `hexify` /
  `numerify` helpers.
- **Every weighted draw goes through `_weighted()`**, which passes
  `use_weighting=True`. `BaseProvider.__use_weighting__` defaults to `False`
  for providers registered via `add_provider()`, so a plain
  `random_element(OrderedDict)` silently ignores the weights and the
  distribution tests will drift.
- Any tuple derived from a set MUST be `sorted()` — set iteration order moves
  with hash randomization.
- Time math is **integer nanoseconds**
  (`(dt - EPOCH) // timedelta(microseconds=1) * 1000`), never
  `dt.timestamp() * 1e9` (float64 loses precision at nanosecond scale).
- Changing the **order** of RNG draws inside an existing method changes the
  output of already-seeded user fixtures. Avoid it; if it is unavoidable, say
  so explicitly in the PR description so it can go in the release notes.

What must stay reproducible: with the same seed and an explicit `start_time`,
`trace()` output is byte-identical (ids, tree shape, durations, statuses); with
the default `start_time`, ids and structure still reproduce, only the anchor
timestamp moves. `log_line()` rendered from the same record is byte-identical.
`tests/test_scenario_seeding.py` guards all of this.

## Trace contract

`trace()` must keep emitting a tree a real OTel deployment could have emitted:

- one `trace_id`; unique span ids; a single root, emitted first;
- children time-contained inside their parent; sequential siblings never
  overlap;
- every CLIENT hop paired with exactly one SERVER child, with matching HTTP
  status;
- every cross-service edge present in `SERVICE_CORRELATIONS` (which must stay
  a **DAG**);
- error traces: exactly one origin span carries the `exception` event, its
  `exception.type` comes from the **owning service's** `error_types` and the
  stacktrace matches that service's language; every ancestor on the root path
  is ERROR with 5xx / non-zero gRPC codes; off-path spans stay UNSET
  (successful spans are UNSET, not OK — that is SDK-faithful);
- span and attribute names are **copied from the OTel semantic conventions,
  never invented**: HTTP server `{method} {route}`, HTTP client bare
  `{method}`, gRPC `/{package}.{Service}/{Method}`, DB `{operation} {target}`
  (bare command for Redis), messaging `publish {destination}`;
- `otlp_json()` follows the OTLP/JSON encoding: lowerCamelCase keys, hex id
  strings, integer kind enums, int64 timestamps as decimal strings, typed
  attribute values, UNSET status as `{}`.

## Log contract

- `log_record()` always populates every field (empty string / `0` when not
  applicable) so any of the 9 formats can render from any record.
- A record correlated with a span carries that span's `trace_id` / `span_id`;
  an uncorrelated record leaves both empty, and the renderers must omit the
  correlation fields rather than print empty ones.
- Renderers are byte-level faithful to their spec — RFC 5424 / RFC 3164
  (including the space-padded day and `PRI = facility×8 + severity`), Apache
  CLF (`%b` renders zero bytes as `-`) and error-log, nginx error-log,
  logfmt, JSON. A new format needs a renderer test that asserts the exact
  grammar, not just "it contains the message".

## Data and catalog rules

- Catalog updates are **additive by default**: never remove or rename an
  existing service or operation unless a maintainer asks for it or it is a
  verified mistake — downstream fixtures pin these names.
- Adding a service requires: the DAG preserved; `error_types` ⊆
  `EXCEPTION_TYPES[language]` in `constants.py`; semconv-correct operation
  names; `latency_ms` as `(p50, p95)` with `0 < p50 <= p95`; and the service
  count in the `service_correlations.py` docstring updated.
- **Verify facts, don't invent them.** Formats, header grammars, attribute
  keys and status codes are copied from the spec, with the spec named in the
  PR description. Entities that are newer than a model's training data can be
  perfectly real — confirm against the spec or vendor docs instead of
  assuming they are fake.
- **No real trademarks or real telemetry.** Application services are generic
  role names (`checkout-service`, `payment-service`); infrastructure entries
  are open-source components named descriptively (`postgres`, `redis`,
  `kafka`). Do not add vendor or product brand names, customer names, or
  anything that could read as a real company's infrastructure.

## Tests expected with new data

- Catalog-integrity, trace-invariant and OTLP-encoding suites are generic —
  a new service or operation is picked up automatically, so **run the full
  suite and expect it to stay green** without editing assertions. Needing to
  weaken an existing assertion is a signal the data is wrong, not the test.
- Add targeted tests for anything the generic suites cannot see:
  - a new **correlation** (e.g. a new attribute derived from another field)
    gets an assertion that ties the two together, the way
    `test_resource_attributes_internal_consistency` and
    `test_log_span_ids_belong_to_the_trace` do;
  - a new **weighted pool** gets a distribution test over a seeded sample
    (see `test_log_level_values_and_info_dominance`), so a lost
    `use_weighting=True` fails loudly;
  - a new **log format** gets a grammar test, plus its entry in the format
    list;
  - a new **language** for stacktraces/exceptions gets a format test per
    frame shape and an `EXCEPTION_TYPES` pool entry.
- This provider ships no locale-specific data, so there is no per-locale
  coverage requirement. The equivalent obligation here is per-format and
  per-language coverage: every value in `_LOG_FORMATS` and every key in
  `EXCEPTION_TYPES` must be exercised by a test.

## Provenance and licensing for external catalogues

If you bring in data from outside this repo:

- Name the source and its version/date in the PR description and, when it is
  a spec, in the *Verification sources* section of `AGENTS.md`.
- Only public specifications and permissively licensed sources — anything MIT
  or otherwise compatible with this repo's MIT license. Do not paste in data
  under a share-alike, non-commercial or no-derivatives license, and do not
  bulk-copy a proprietary vendor catalogue.
- Copy identifiers and grammars exactly (they are facts); do not copy prose,
  tables or wholesale extracts of a licensed document.
- Keep generated values synthetic: derive names, hostnames and ids from the
  generators here rather than shipping a dump of real-world records.

## Pull requests

- One focused change per PR. Keep a mechanical reformat in its own commit,
  separate from substantive edits.
- Run the four checks above before pushing and mention anything that had to
  change in the RNG draw order.
- Don't bump the version in a feature PR: releases are cut by the maintainer
  via a `v*` tag (see the release checklist in `AGENTS.md`).

"""Catalog integrity: shapes, enums, DAG topology, derived provider views."""

import pytest
from faker import Faker

from faker_observability import ObservabilityProvider
from faker_observability.constants import EXCEPTION_TYPES
from faker_observability.service_correlations import SERVICE_CORRELATIONS


@pytest.fixture
def provider() -> ObservabilityProvider:
    fake = Faker()
    fake.add_provider(ObservabilityProvider)
    return ObservabilityProvider(fake)


REQUIRED_KEYS = {"kind", "language", "version", "operations", "dependencies", "latency_ms", "error_types"}
VALID_KINDS = {"http", "grpc", "db", "cache", "queue", "worker"}
VALID_LANGUAGES = {"python", "java", "javascript", "go", "native"}


class TestCatalogIntegrity:
    def test_all_entries_complete(self) -> None:
        for name, data in SERVICE_CORRELATIONS.items():
            assert set(data) == REQUIRED_KEYS, name
            assert data["operations"], name
            assert data["version"], name

    def test_kind_enum(self) -> None:
        for name, data in SERVICE_CORRELATIONS.items():
            assert data["kind"] in VALID_KINDS, name

    def test_language_enum(self) -> None:
        for name, data in SERVICE_CORRELATIONS.items():
            assert data["language"] in VALID_LANGUAGES, name

    def test_dependencies_exist(self) -> None:
        for name, data in SERVICE_CORRELATIONS.items():
            for dependency in data["dependencies"]:
                assert dependency in SERVICE_CORRELATIONS, f"{name} -> {dependency}"

    def test_dependency_graph_is_dag(self) -> None:
        WHITE, GRAY, BLACK = 0, 1, 2
        color = dict.fromkeys(SERVICE_CORRELATIONS, WHITE)

        def visit(node: str, path: tuple[str, ...]) -> None:
            if color[node] == GRAY:
                raise AssertionError(f"dependency cycle: {' -> '.join(path + (node,))}")
            if color[node] == BLACK:
                return
            color[node] = GRAY
            for dependency in SERVICE_CORRELATIONS[node]["dependencies"]:
                visit(dependency, path + (node,))
            color[node] = BLACK

        for name in SERVICE_CORRELATIONS:
            visit(name, ())

    def test_latency_bands(self) -> None:
        for name, data in SERVICE_CORRELATIONS.items():
            p50, p95 = data["latency_ms"]
            assert 0 < p50 <= p95, name

    def test_error_types_subset_of_language_pool(self) -> None:
        for name, data in SERVICE_CORRELATIONS.items():
            if data["language"] == "native":
                assert data["error_types"] == [], name
            else:
                assert data["error_types"], name
                assert set(data["error_types"]) <= set(EXCEPTION_TYPES[data["language"]]), name

    def test_native_services_have_no_dependencies(self) -> None:
        for name, data in SERVICE_CORRELATIONS.items():
            if data["language"] == "native":
                assert data["dependencies"] == [], name

    def test_entry_services(self, provider: ObservabilityProvider) -> None:
        assert provider.entry_services
        for name in provider.entry_services:
            assert SERVICE_CORRELATIONS[name]["kind"] in ("http", "grpc")

    def test_derived_properties_match_catalog(self, provider: ObservabilityProvider) -> None:
        assert provider.services == tuple(sorted(SERVICE_CORRELATIONS))
        assert provider.all_operations == tuple(sorted({op for data in SERVICE_CORRELATIONS.values() for op in data["operations"]}))
        assert provider.services_by_kind("queue") == ("kafka",)
        with pytest.raises(ValueError):
            provider.services_by_kind("mesh")

    def test_derived_views_are_properties_not_stored_copies(self) -> None:
        for attribute in ("services", "entry_services", "all_operations", "service_correlations"):
            assert isinstance(vars(ObservabilityProvider)[attribute], property), attribute

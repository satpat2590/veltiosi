"""Tests for the data-source connector registry (fail-open contract)."""

from __future__ import annotations

from veltiosi.connectors.datasources import REGISTRY, query_source


def test_registry_has_all_omni_sources():
    assert set(REGISTRY.keys()) == {"whoop", "edoras", "raga", "itihasa", "atma"}


def test_unknown_source_returns_none():
    assert query_source("nope", "question") is None


def test_query_source_fail_open_on_bad_source():
    # returning None (not raising) is the contract for a missing/unreachable source
    assert query_source("unknown-source", "q") is None
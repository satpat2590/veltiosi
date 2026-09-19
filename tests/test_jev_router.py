"""Tests for the Jev query router.

Verifies the "natural language DB search" routing contract against a mocked
client: fail-open neutral route, intent/domain/data-source parsing, category
mapping, and semantic re-rank. No network I/O.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from veltiosi.indexing.jev_router import JevQueryRouter, RoutingDecision
from veltiosi.models import RootCategory


def _client(answers=None, enabled=True):
    c = MagicMock()
    c.enabled = enabled
    c.decide.return_value = answers
    return c


FULL_ANSWERS = {
    "intent": {"choice": "fact_lookup", "confidence": 0.94},
    "domain": {"choice": "financial", "probabilities": {"financial": 0.9, "mental": 0.05}},
    "data_source": {"choice": "vault"},
    "answerable": {"noul": 0.6},
}


class TestRoute:
    def test_disabled_returns_neutral(self):
        r = JevQueryRouter(client=_client(enabled=False)).route("what is X?")
        assert r.available is False
        assert r.intent == "synthesis"  # conservative default -> Gemini
        assert r.data_source == "vault"
        assert r.category_filter is None

    def test_error_returns_neutral(self):
        r = JevQueryRouter(client=_client(answers=None, enabled=True)).route("what is X?")
        assert r.available is False
        assert r.source == "error"

    def test_parses_full_route(self):
        r = JevQueryRouter(client=_client(FULL_ANSWERS)).route("what did we decide?")
        assert r.available is True
        assert r.intent == "fact_lookup"
        assert r.intent_confidence == pytest.approx(0.94)
        assert r.domain == "financial"
        assert r.data_source == "vault"
        assert r.answerable == pytest.approx(0.6)

    def test_category_filter_maps_domain(self):
        r = JevQueryRouter(client=_client(FULL_ANSWERS)).route("q")
        assert r.category_filter is RootCategory.FINANCIAL

    def test_uncertain_domain_has_no_filter(self):
        answers = dict(FULL_ANSWERS, domain={"choice": "uncertain", "probabilities": {}})
        r = JevQueryRouter(client=_client(answers)).route("q")
        assert r.domain == "uncertain"
        assert r.category_filter is None

    def test_secondary_domains_from_probabilities(self):
        answers = {
            "intent": {"choice": "synthesis"},
            "domain": {"choice": "mental", "probabilities": {"mental": 0.8, "social": 0.3, "financial": 0.1}},
            "data_source": {"choice": "vault"},
            "answerable": {"noul": 0.1},
        }
        r = JevQueryRouter(client=_client(answers)).route("q")
        assert "social" in r.secondary_domains
        assert "financial" not in r.secondary_domains  # below 0.2 threshold


class TestRerank:
    ANSWER_R0 = {"r0": {"noul": 0.2}, "r1": {"noul": 0.9}, "r2": {"noul": 0.5}}

    def test_sorts_by_jscore(self):
        items = [
            {"id": "a", "title": "A", "snippet": "alpha"},
            {"id": "b", "title": "B", "snippet": "beta"},
            {"id": "c", "title": "C", "snippet": "gamma"},
        ]
        out = JevQueryRouter(client=_client(self.ANSWER_R0)).rerank("q", items)
        assert [o["id"] for o in out] == ["b", "c", "a"]
        assert out[0]["jscore"] == 0.9

    def test_disabled_returns_copy_unchanged(self):
        items = [{"id": "a", "title": "A", "snippet": "x"}]
        out = JevQueryRouter(client=_client(enabled=False)).rerank("q", items)
        assert out == items
        assert "jscore" not in out[0]

    def test_empty_items(self):
        assert JevQueryRouter(client=_client(self.ANSWER_R0)).rerank("q", []) == []
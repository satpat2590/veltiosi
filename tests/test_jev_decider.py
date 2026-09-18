"""Tests for the generic JevDecider primitives.

Verifies the reusable "code in Jev" surface: choice/noul/score parsing, the
guaranteed fallback Decision (never None), and the distribution helpers
(argmax / entropy / expectation / confident). Client is mocked — no network.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from veltiosi.indexing.jev_decider import JevDecider, Decision


def _client(answers=None, enabled=True):
    c = MagicMock()
    c.enabled = enabled
    c.decide.return_value = answers
    return c


class TestChoice:
    def test_parses_probabilities_and_confidence(self):
        ans = {"x": {"choice": "bull", "probabilities": {"bull": 0.8, "bear": 0.2}, "confidence": 0.8}}
        d = JevDecider(client=_client(ans)).choice("state", {"bull": "up", "bear": "down"})
        assert d.argmax == "bull"
        assert d.source == "jev"
        assert d.available is True
        assert d.confidence == 0.8

    def test_fallback_when_client_none(self):
        d = JevDecider(client=_client(None)).choice("state", {"bull": "up", "bear": "down"})
        assert d.available is False
        assert d.source == "fallback"
        assert d.argmax in {"bull", "bear"}  # uniform fallback is non-empty

    def test_disabled_returns_fallback(self):
        d = JevDecider(client=_client(enabled=False)).choice("s", {"a": "x", "b": "y"})
        assert d.available is False


class TestNoul:
    def test_true_false_distribution(self):
        ans = {"x": {"noul": 0.9}}
        d = JevDecider(client=_client(ans)).noul("state", "Is this true?")
        assert d.distribution["true"] == 0.9
        assert abs(d.distribution["false"] - 0.1) < 1e-9


class TestScore:
    def test_relabels_indices_to_rubric(self):
        ans = {"x": {"score": 1.4, "probabilities": {"0": 0.6, "1": 0.4, "2": 0.0}}}
        rubric = ["Low", "Medium", "High"]
        d = JevDecider(client=_client(ans)).score("state", rubric, "how much?")
        assert "Medium" in d.distribution
        assert d.distribution["Medium"] == 0.4

    def test_expectation_over_rubric_index(self):
        ans = {"x": {"probabilities": {"0": 0.0, "1": 0.0, "2": 1.0}}}
        rubric = ["Low", "Med", "High"]
        d = JevDecider(client=_client(ans)).score("state", rubric, "how much?")
        sig = d.expectation({rubric[i]: i for i in range(len(rubric))})
        assert sig == 2.0


class TestDecisionHelpers:
    def test_entropy(self):
        flat = Decision({"a": 0.5, "b": 0.5}, source="jev")
        peak = Decision({"a": 1.0, "b": 0.0}, source="jev")
        assert flat.entropy() > peak.entropy()

    def test_confident(self):
        assert Decision({"a": 1.0}, confidence=0.95, source="jev").confident(0.9) is True
        assert Decision({"a": 1.0}, confidence=0.6, source="jev").confident(0.9) is False
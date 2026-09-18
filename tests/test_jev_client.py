"""Tests for the fail-open Jev client.

Covers the happy path AND every failure mode the skill requires: no key,
flag-off, HTTP error, transport error, non-JSON body, and missing ``answers``.
No real network I/O — ``requests.post`` is mocked. The ambient-env trap is
pinned with explicit ``api_key=``/``enabled=`` constructor args so a stray
``OPENROUTER_API_KEY`` in the shell cannot flip a "disabled" assertion.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from veltiosi.indexing.jev_client import JevClient

# Pin the ambient-env precondition: a live verification run that `source`s
# ~/.hermes/.env exports OPENROUTER_API_KEY into the persistent shell, which
# would otherwise flip any "disabled without key" assertion. Deleting the vars
# for every test in this module makes the suite immune to that leak.
@pytest.fixture(autouse=True)
def _pin_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("VELTIOSI_JEV_API_KEY", raising=False)
    monkeypatch.delenv("VELTIOSI_JEV_ENABLED", raising=False)


GOOD_ANSWERS = {
    "root": {
        "type": "choice",
        "choice": "mental",
        "probabilities": {"mental": 0.98, "social": 0.01, "financial": 0.01},
        "confidence": 0.97,
    }
}


def _resp(status=200, body=None):
    r = MagicMock()
    r.status_code = status
    r.text = "" if body is None else json.dumps(body)
    r.json.return_value = body
    return r


class TestEnabledState:
    def test_disabled_without_key(self):
        c = JevClient(api_key=None, enabled=True)
        assert c.enabled is False

    def test_enabled_with_key(self):
        c = JevClient(api_key="sk-test", enabled=True)
        assert c.enabled is True

    def test_flag_off_disables_even_with_key(self):
        c = JevClient(api_key="sk-test", enabled=False)
        assert c.enabled is False


class TestDecideFailureModes:
    def test_returns_none_when_disabled(self):
        c = JevClient(api_key=None, enabled=True)
        assert c.decide("state", {"q": {"type": "noul", "instructions": "x"}}) is None

    @patch("veltiosi.indexing.jev_client.requests")
    def test_happy_path_returns_answers(self, mock_requests):
        mock_requests.post.return_value = _resp(200, {"answers": GOOD_ANSWERS})
        c = JevClient(api_key="sk-test", enabled=True)
        ans = c.decide("state", {"root": {"type": "choice", "criteria": {}}})
        assert ans == GOOD_ANSWERS

    @patch("veltiosi.indexing.jev_client.requests")
    def test_http_error_returns_none(self, mock_requests):
        mock_requests.post.return_value = _resp(401, {"error": "bad key"})
        c = JevClient(api_key="sk-test", enabled=True)
        assert c.decide("state", {"q": {"type": "noul", "instructions": "x"}}) is None

    @patch("veltiosi.indexing.jev_client.requests")
    def test_transport_error_returns_none(self, mock_requests):
        mock_requests.post.side_effect = RuntimeError("connection reset")
        c = JevClient(api_key="sk-test", enabled=True)
        assert c.decide("state", {"q": {"type": "noul", "instructions": "x"}}) is None

    @patch("veltiosi.indexing.jev_client.requests")
    def test_non_json_returns_none(self, mock_requests):
        r = MagicMock()
        r.status_code = 200
        r.text = "not json"
        r.json.side_effect = ValueError("no json")
        mock_requests.post.return_value = r
        c = JevClient(api_key="sk-test", enabled=True)
        assert c.decide("state", {"q": {"type": "noul", "instructions": "x"}}) is None

    @patch("veltiosi.indexing.jev_client.requests")
    def test_missing_answers_returns_none(self, mock_requests):
        mock_requests.post.return_value = _resp(200, {"model": "jev-1.13"})
        c = JevClient(api_key="sk-test", enabled=True)
        assert c.decide("state", {"q": {"type": "noul", "instructions": "x"}}) is None
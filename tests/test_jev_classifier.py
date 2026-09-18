"""Tests for the Jev note classifier.

Verifies the classification contract against a mocked client (no network): the
raw-evidence state, the fan-out question schema, answer parsing into a typed
``JevClassification``, the subcategory threshold, and the fail-open degrade when
Jev is disabled or errors.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from veltiosi.indexing.jev_classifier import JevNoteClassifier, JevClassification

FULL_ANSWERS = {
    "root": {
        "type": "choice",
        "choice": "mental",
        "probabilities": {"mental": 0.95, "social": 0.03, "financial": 0.02},
        "confidence": 0.94,
    },
    "note_type": {
        "type": "choice",
        "choice": "concept",
        "probabilities": {"concept": 0.9, "uncertain": 0.1},
        "confidence": 0.88,
    },
    "requires_slope": {"type": "noul", "noul": 0.91},
    "cross_domain": {"type": "noul", "noul": 0.74},
}


def _mock_client(answers=None, enabled=True):
    client = MagicMock()
    client.enabled = enabled
    client.decide.return_value = answers
    return client


class TestStateRendering:
    def test_strips_frontmatter(self):
        content = "---\ntags: [x]\ndate: 2026-01-01\n---\n\n# Body here"
        state = JevNoteClassifier.render_state("My Note", content)
        assert "Body here" in state["body"]
        assert "tags:" not in state["body"]

    def test_caps_body_length(self):
        content = "word " * 5000
        state = JevNoteClassifier.render_state("T", content)
        assert len(state["body"]) <= 1500
        assert state["title"] == "T"


class TestQuestionSchema:
    def test_fan_out_includes_choice_and_nouls(self):
        c = JevNoteClassifier(client=_mock_client())
        q = c.build_questions()
        assert q["root"]["type"] == "choice"
        assert q["note_type"]["type"] == "choice"
        assert q["requires_slope"]["type"] == "noul"
        assert q["cross_domain"]["type"] == "noul"
        # one noul per configured subcategory
        n_sub = len([k for k in q if k.startswith("sub_")])
        from veltiosi.settings import settings

        assert n_sub == len(settings.subcategories)


class TestClassification:
    def test_disabled_returns_unavailable(self):
        c = JevNoteClassifier(client=_mock_client(enabled=False))
        r = c.classify("T", "body")
        assert isinstance(r, JevClassification)
        assert r.available is False
        assert r.source == "disabled"

    def test_error_returns_unavailable(self):
        c = JevNoteClassifier(client=_mock_client(answers=None, enabled=True))
        r = c.classify("T", "body")
        assert r.available is False
        assert r.source == "error"

    def test_parses_full_answers(self):
        # attach subcategory nouls for all configured subcategories
        from veltiosi.settings import settings

        answers = dict(FULL_ANSWERS)
        for name in settings.subcategories:
            answers[f"sub_{name}"] = {"type": "noul", "noul": 0.0}
        answers["sub_research"] = {"type": "noul", "noul": 0.8}
        answers["sub_ml_ops"] = {"type": "noul", "noul": 0.6}

        c = JevNoteClassifier(client=_mock_client(answers=answers, enabled=True))
        r = c.classify("Emergence", "# Emergence\n\nConsciousness via CA")
        assert r.available is True
        assert r.root == "mental"
        assert r.root_confidence == pytest.approx(0.94)
        assert r.note_type == "concept"
        assert r.requires_slope == pytest.approx(0.91)
        assert r.cross_domain == pytest.approx(0.74)
        assert "research" in r.subcategories
        assert "ml_ops" in r.subcategories

    def test_subcategory_threshold_filters(self):
        from veltiosi.settings import settings

        answers = dict(FULL_ANSWERS)
        for name in settings.subcategories:
            answers[f"sub_{name}"] = {"type": "noul", "noul": 0.0}
        answers["sub_ml_ops"] = {"type": "noul", "noul": 0.49}  # below default 0.5

        c = JevNoteClassifier(client=_mock_client(answers=answers, enabled=True))
        r = c.classify("T", "body")
        assert "ml_ops" not in r.subcategories

    def test_confidence_gate(self):
        confident = JevClassification(
            available=True, source="jev", root_confidence=0.9
        )
        unsure = JevClassification(available=True, source="jev", root_confidence=0.3)
        assert confident.root_confident(0.55) is True
        assert unsure.root_confident(0.55) is False
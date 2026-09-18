"""Jev note classifier — calibrated, confidence-aware classification.

Complements the deterministic ``NoteClassifier`` (keyword matching). Jev reads
the RAW note (title + body) and returns calibrated probabilities over the
taxonomy (root categories, note types, subcategories) plus slope / cross-domain
signals. The root + subcategory taxonomy is **config-driven**: expanding
``categories.yaml`` / ``subcategories.yaml`` automatically widens the space Jev
can classify — no code change.

Code owns thresholds; the folder->root mapping stays a deterministic floor.
Low-confidence answers escalate to review instead of being auto-applied. Jev is
ADVISORY and fail-open: a disabled/erroring client yields an "unavailable"
classification (``source`` "disabled"/"error") that callers degrade to the
keyword result. The output carries the full distribution + confidence + a
secondary-root read so downstream can do multi-label and ordering.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..settings import settings
from .jev_client import JevClient

logger = logging.getLogger(__name__)

# Note type is a stable axis (concept/synthesis/journal/...): it changes with
# schema design, not with topic breadth, so it stays an explicit constant.
NOTE_TYPE_CRITERIA: Dict[str, str] = {
    "concept": "A standalone idea, argument, or philosophical exploration — one coherent thought developed in one place. Most essays and idea notes are concept notes.",
    "source_summary": "A summary of an external source (article, paper, book, podcast, video)",
    "compounding_page": "A running log or journal entry that records daily or ongoing activity and grows incrementally (a daily note, a diary, a changelog, a task-linked accumulation). NOT a standalone essay.",
    "synthesis": "An essay that weaves MULTIPLE distinct existing ideas or threads together into a new whole",
    "moc": "A map-of-content / index that lists links to other pages",
    "task_linked": "A note tied to a specific task or deliverable",
    "reference": "Reference material (a definition, a lookup, a citation, a fact)",
    "generated_index": "A generated index or catalog",
    "uncertain": "None of the above clearly fits",
}

# Leading "YYYY-MM-DD - " date stamp leaks a spurious "journal entry" signal.
_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s*[-–—:]\s*")


def build_root_criteria() -> Dict[str, str]:
    """Root-category criteria, driven entirely by ``settings.root_categories``.

    Each entry reads ``display_name`` + ``description`` straight from
    ``categories.yaml``, so adding a root there automatically extends the Choice
    space Jev can assign. ``uncertain`` is always appended so the model can
    decline rather than force a closest-but-wrong label.
    """
    criteria: Dict[str, str] = {}
    for name, cfg in settings.root_categories.items():
        label = cfg.display_name or name
        desc = (cfg.description or "").strip()
        criteria[name] = f"{label}: {desc}" if desc else label
    criteria["uncertain"] = "None of the above clearly fits"
    return criteria


@dataclass
class JevClassification:
    """The calibrated result of one note classification.

    ``available`` is True only when Jev actually returned answers; otherwise the
    object holds ``source="disabled"`` / ``source="error"`` and empty fields, so
    callers never branch on ``None``. ``secondary_roots`` is a multi-label read
    off the root probability mass (a note can genuinely span roots).
    """

    available: bool = False
    source: str = "disabled"

    root: Optional[str] = None
    root_probabilities: Dict[str, float] = field(default_factory=dict)
    root_confidence: Optional[float] = None
    secondary_roots: List[str] = field(default_factory=list)

    note_type: Optional[str] = None
    note_type_probabilities: Dict[str, float] = field(default_factory=dict)
    note_type_confidence: Optional[float] = None

    requires_slope: Optional[float] = None
    cross_domain: Optional[float] = None

    subcategories: List[str] = field(default_factory=list)
    subcategory_probs: Dict[str, float] = field(default_factory=dict)

    def root_confident(self, threshold: float) -> bool:
        return bool(
            self.available
            and self.root_confidence is not None
            and self.root_confidence >= threshold
        )

    def type_confident(self, threshold: float) -> bool:
        return bool(
            self.available
            and self.note_type_confidence is not None
            and self.note_type_confidence >= threshold
        )


class JevNoteClassifier:
    """Classify a note's taxonomy with calibrated probabilities."""

    def __init__(
        self,
        client: Optional[JevClient] = None,
        subcategory_threshold: float = 0.5,
        secondary_root_threshold: float = 0.2,
    ) -> None:
        self.client = client or JevClient()
        self.subcategory_threshold = subcategory_threshold
        self.secondary_root_threshold = secondary_root_threshold

    @property
    def enabled(self) -> bool:
        return bool(self.client.enabled)

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        """Drop a leading YAML frontmatter block to reduce noise/tokens."""
        if not content.lstrip().startswith("---"):
            return content
        stripped = content.lstrip()
        end = stripped.find("\n---", 3)
        if end == -1:
            return content
        return stripped[end + 4 :]

    @staticmethod
    def _clean_title(title: str) -> str:
        """Strip a leading date stamp (a leak that biases note_type to 'journal')."""
        trimmed = title.strip()
        cleaned = _DATE_PREFIX_RE.sub("", trimmed)
        return cleaned or trimmed

    @staticmethod
    def render_state(title: str, content: str, body_limit: int = 1500) -> Dict[str, str]:
        """Build the compact state Jev evaluates (title + filtered body).

        We send RAW evidence (not the deterministic folder->root mapping) so Jev
        forms an independent judgment; the folder mapping is reconciled in code.
        Body is capped to avoid context rot. The leading date stamp is stripped
        so it is not misread as a journal/daily entry.
        """
        body = JevNoteClassifier._strip_frontmatter(content).strip()
        body = body[:body_limit]
        return {"title": JevNoteClassifier._clean_title(title), "body": body}

    def build_questions(self) -> Dict[str, Dict[str, Any]]:
        """One fan-out set: all dimensions asked in a single round-trip.

        Root + note_type are `choice` (single-label, confidence-gated). Root
        criteria come from config so the topic space is extensible.
        Subcategories are independent `noul` probes (a note can belong to
        several); they are features, not a clean PMF.
        """
        questions: Dict[str, Dict[str, Any]] = {
            "root": {
                "type": "choice",
                "instructions": "Which root category best fits this note?",
                "criteria": build_root_criteria(),
            },
            "note_type": {
                "type": "choice",
                "instructions": "What kind of note is this?",
                "criteria": dict(NOTE_TYPE_CRITERIA),
            },
            "requires_slope": {
                "type": "noul",
                "instructions": (
                    "This note captures a rate-of-change or process insight "
                    "(a slope, a trajectory, an emergence, how something evolves) "
                    "rather than a static snapshot or fixed fact"
                ),
            },
            "cross_domain": {
                "type": "noul",
                "instructions": (
                    "This note meaningfully spans more than one root category or domain"
                ),
            },
        }
        for name, cfg in settings.subcategories.items():
            desc = (cfg.description or "").strip()
            instruction = f"This note pertains to {cfg.display_name}."
            if desc:
                instruction += f" {desc}"
            questions[f"sub_{name}"] = {"type": "noul", "instructions": instruction}
        return questions

    def classify(self, title: str, content: str) -> JevClassification:
        """Classify one note; never raises, never returns ``None``.

        Returns an ``available=False`` classification when Jev is disabled or
        errors, so callers degrade to the deterministic result.
        """
        if not self.enabled:
            return JevClassification(available=False, source="disabled")

        state = self.render_state(title, content)
        questions = self.build_questions()
        answers = self.client.decide(state, questions)
        if answers is None:
            return JevClassification(available=False, source="error")

        return self.from_answers(answers)

    def from_answers(self, answers: Dict[str, Any]) -> JevClassification:
        """Parse the raw ``answers`` dict into a typed ``JevClassification``."""
        result = JevClassification(available=True, source="jev")

        root = answers.get("root") or {}
        if isinstance(root, dict):
            result.root = root.get("choice")
            probs = root.get("probabilities")
            if isinstance(probs, dict):
                result.root_probabilities = {str(k): float(v) for k, v in probs.items()}
            if root.get("confidence") is not None:
                result.root_confidence = float(root["confidence"])

        # Multi-label read: any root with meaningful probability mass (besides the
        # argmax and the "uncertain" escape hatch) is a secondary root.
        if result.root and result.root_probabilities:
            result.secondary_roots = [
                k
                for k, v in result.root_probabilities.items()
                if k not in (result.root, "uncertain") and v >= self.secondary_root_threshold
            ]

        note_type = answers.get("note_type") or {}
        if isinstance(note_type, dict):
            result.note_type = note_type.get("choice")
            probs = note_type.get("probabilities")
            if isinstance(probs, dict):
                result.note_type_probabilities = {str(k): float(v) for k, v in probs.items()}
            if note_type.get("confidence") is not None:
                result.note_type_confidence = float(note_type["confidence"])

        slope = answers.get("requires_slope") or {}
        if isinstance(slope, dict) and slope.get("noul") is not None:
            result.requires_slope = float(slope["noul"])

        cross = answers.get("cross_domain") or {}
        if isinstance(cross, dict) and cross.get("noul") is not None:
            result.cross_domain = float(cross["noul"])

        for name in settings.subcategories:
            ans = answers.get(f"sub_{name}") or {}
            p = ans.get("noul") if isinstance(ans, dict) else None
            if p is not None:
                result.subcategory_probs[name] = float(p)

        result.subcategories = [
            name
            for name, p in result.subcategory_probs.items()
            if p >= self.subcategory_threshold
        ]

        return result
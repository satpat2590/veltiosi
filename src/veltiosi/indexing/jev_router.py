"""Jev query router — classify a natural-language query, route to the right handler.

The "natural language DB search" pattern: Jev does NOT run the query. It
classifies the query's intent, knowledge domain, target data source, and
answerability — then CODE routes to the cheapest correct handler (deterministic
lookup / a specific data store / the generative LLM / a clarifying follow-up).

Fail-open: a disabled or erroring Jev yields a neutral ``RoutingDecision``
(intent="synthesis", data_source="vault") so the existing Gemini path runs
byte-for-byte unchanged when the key is absent or Jev is down.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models import RootCategory
from .jev_classifier import build_root_criteria
from .jev_client import JevClient

logger = logging.getLogger(__name__)

INTENT_CRITERIA: Dict[str, str] = {
    "fact_lookup": "A precise factual lookup or status check (a decision, a date, a definition, a metric, 'where is X', 'what did we decide')",
    "synthesis": "Needs reasoning or analysis across multiple notes to form a new answer or summary",
    "navigation": "Finding a specific note or page by name or topic",
    "clarify": "The question is ambiguous or underspecified and needs a follow-up before it can be answered",
}

DATA_SOURCE_CRITERIA: Dict[str, str] = {
    "vault": "Knowledge in the Obsidian vault — notes, decisions, research, philosophy",
    "whoop": "Health/body metrics — strain, recovery, sleep, workouts",
    "edoras": "Trading/finance — portfolios, signals, trades, market data",
    "atma": "Tasks, learning, points, skill tree",
    "raga": "Music / Spotify listening data",
    "itihasa": "History — events, eras, patterns across time",
    "external": "Current or up-to-date facts that need the live web, not stored data",
    "uncertain": "Cannot tell which source this needs",
}


@dataclass
class RoutingDecision:
    """Jev's classification of a query; ``available=False`` means Jev was absent.

    Defaults are the conservative route: synthesis -> Gemini, vault -> vault
    retrieval, so a missing Jev changes nothing.
    """

    available: bool = False
    source: str = "disabled"

    intent: str = "synthesis"
    intent_confidence: Optional[float] = None

    domain: Optional[str] = None
    secondary_domains: List[str] = field(default_factory=list)

    data_source: str = "vault"
    answerable: float = 0.5

    @property
    def category_filter(self) -> Optional[RootCategory]:
        if not self.domain:
            return None
        try:
            return RootCategory(self.domain)
        except ValueError:
            return None


class JevQueryRouter:
    """Route a query with Jev; re-rank a retrieval shortlist with Jev."""

    def __init__(self, client: Optional[JevClient] = None) -> None:
        self.client = client or JevClient()

    @property
    def enabled(self) -> bool:
        return bool(self.client.enabled)

    def route(self, question: str) -> RoutingDecision:
        if not self.enabled:
            return RoutingDecision(available=False, source="disabled")

        questions = {
            "intent": {"type": "choice", "instructions": "What does this query need?",
                       "criteria": INTENT_CRITERIA},
            "domain": {"type": "choice", "instructions": "Which knowledge domain does this span?",
                       "criteria": build_root_criteria()},
            "data_source": {"type": "choice", "instructions": "Which data store would answer this?",
                            "criteria": DATA_SOURCE_CRITERIA},
            "answerable": {"type": "noul",
                           "instructions": "Can this be answered by notes retrieved from the vault alone, without additional reasoning?"},
        }
        answers = self.client.decide(question, questions)
        if answers is None:
            return RoutingDecision(available=False, source="error")

        intent = answers.get("intent") or {}
        domain = answers.get("domain") or {}
        source = answers.get("data_source") or {}
        answerable = answers.get("answerable") or {}

        decision = RoutingDecision(available=True, source="jev")
        if isinstance(intent, dict):
            decision.intent = intent.get("choice") or "synthesis"
            if intent.get("confidence") is not None:
                decision.intent_confidence = float(intent["confidence"])
        if isinstance(domain, dict):
            decision.domain = domain.get("choice")
            probs = domain.get("probabilities") or {}
            ranked = sorted(probs.items(), key=lambda kv: -float(kv[1]))
            decision.secondary_domains = [k for k, v in ranked if k != decision.domain and float(v) >= 0.2]
        if isinstance(source, dict):
            decision.data_source = source.get("choice") or "vault"
        if isinstance(answerable, dict) and answerable.get("noul") is not None:
            decision.answerable = float(answerable["noul"])

        return decision

    def rerank(self, query: str, items: List[Dict[str, str]], top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Re-rank a retrieval shortlist by Jev relevance (one fan-out call).

        ``items`` is ``[{id, title, snippet}, ...]``. Returns a copy sorted by a
        ``jscore`` (calibrated relevance 0..1) with the score appended.
        """
        if not self.enabled or not items:
            return [dict(it) for it in items]

        questions = {}
        for i, it in enumerate(items):
            title = (it.get("title") or "").strip()
            snippet = (it.get("snippet") or "").strip()[:400]
            questions[f"r{i}"] = {
                "type": "noul",
                "instructions": (
                    f"Query: \"{query}\". Item: \"{title}\" — {snippet}. "
                    "Does this item help answer the query?"
                ),
            }
        answers = self.client.decide(query, questions) or {}
        scored = []
        for i, it in enumerate(items):
            p = (answers.get(f"r{i}") or {}).get("noul")
            out: Dict[str, Any] = dict(it)
            out["jscore"] = round(float(p), 3) if p is not None else 0.5
            scored.append(out)
        scored.sort(key=lambda x: -x["jscore"])
        if top_k:
            scored = scored[:top_k]
        return scored
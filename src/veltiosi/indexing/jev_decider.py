"""\"Code in Jev\" — probabilistic decision primitives with a baked-in fallback.

Reusable across ANY closed-label classification, scoring, or routing task — not
just Veltiosi's fixed taxonomy. This is the extensibility surface: a future
domain (Itihasa history eras, event types, market-condition patterns) defines
its own label set and reuses ``JevDecider`` unchanged.

Mirrors the Edoras pattern (see ``edoras/src/llm/jev_decision.py``) but is
self-contained. The power is the *distribution*, not the argmax:

  * ``sample()``      for dynamism (multi-modal spaces: assets, palettes, routing),
  * ``expectation()`` for smoothness (weighted value replaces a hard if/else),
  * ``entropy()``     for escalation (high entropy = Jev unsure = route to review),
  * ``confident()``   for autonomy (act only above a threshold).

Every call carries an explicit ``fallback`` so callers ALWAYS get a usable
``Decision`` — "Jev is down" is a first-class, designed-into path, not None.
"""

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from .jev_client import JevClient


def _normalize(dist: Optional[Dict[str, float]]) -> Dict[str, float]:
    if not dist:
        return {}
    total = sum(float(v) for v in dist.values())
    if total <= 0:
        return {}
    return {k: float(v) / total for k, v in dist.items()}


def _labels_for(criteria) -> List[str]:
    if isinstance(criteria, dict):
        return list(criteria.keys())
    if isinstance(criteria, (list, tuple)):
        return [str(i) for i in range(len(criteria))]
    return []


def _uniform(criteria) -> Dict[str, float]:
    labels = _labels_for(criteria)
    if not labels:
        return {}
    return {k: 1.0 / len(labels) for k in labels}


class Decision:
    """A calibrated probability mass function over a finite outcome space."""

    def __init__(
        self,
        distribution: Optional[Dict[str, float]] = None,
        confidence: Optional[float] = None,
        source: str = "fallback",
        fallback: Optional[Dict[str, float]] = None,
    ) -> None:
        self.distribution = _normalize(distribution) or _normalize(fallback)
        self.confidence = confidence
        self.source = source
        self.available = bool(distribution) and source == "jev"

    @property
    def argmax(self) -> Optional[str]:
        if not self.distribution:
            return None
        return max(self.distribution, key=lambda k: self.distribution[k])

    def prob(self, key: str) -> float:
        return self.distribution.get(key, 0.0)

    def sample(self, rng=None) -> Optional[str]:
        if not self.distribution:
            return None
        rng = rng or random
        keys = list(self.distribution)
        weights = [self.distribution[k] for k in keys]
        return rng.choices(keys, weights=weights, k=1)[0]

    def top_k(self, k: int = 3) -> List[Tuple[str, float]]:
        return sorted(self.distribution.items(), key=lambda kv: -kv[1])[:k]

    def expectation(self, mapping: Dict[str, float], default: float = 0.0) -> float:
        if not self.distribution:
            return default
        return sum(self.distribution.get(k, 0.0) * v for k, v in mapping.items())

    def entropy(self) -> float:
        return -sum(p * math.log2(p) for p in self.distribution.values() if p > 0)

    def confident(self, threshold: float = 0.9) -> bool:
        return bool(self.confidence is not None and self.confidence >= threshold)

    def __repr__(self) -> str:
        body = {k: round(v, 3) for k, v in self.distribution.items()}
        return f"Decision({body}, conf={self.confidence}, src={self.source})"


class JevDecider:
    """A distribution-returning decision source backed by a ``JevClient``.

    ``choice``/``noul``/``score`` each return a ``Decision`` with a guaranteed
    fallback, so downstream code never handles ``None``.
    """

    def __init__(self, client: Optional[JevClient] = None) -> None:
        self.client = client or JevClient()

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.client, "enabled", False))

    def choice(
        self,
        state: Any,
        criteria: Dict[str, str],
        instructions: str = "Pick the best match.",
        fallback: Optional[Dict[str, float]] = None,
        key: str = "x",
    ) -> Decision:
        questions = {key: {"type": "choice", "instructions": instructions, "criteria": criteria}}
        ans = self.client.decide(state, questions)
        entry = (ans or {}).get(key) or {}
        probs, conf = entry.get("probabilities"), entry.get("confidence")
        if probs:
            return Decision(probs, confidence=conf, source="jev", fallback=fallback)
        return Decision(None, source="fallback", fallback=fallback or _uniform(criteria))

    def noul(
        self,
        state: Any,
        instructions: str,
        fallback: float = 0.5,
        key: str = "x",
    ) -> Decision:
        questions = {key: {"type": "noul", "instructions": instructions}}
        ans = self.client.decide(state, questions)
        entry = (ans or {}).get(key) or {}
        p = entry.get("noul")
        if p is not None:
            return Decision({"true": float(p), "false": 1 - float(p)}, source="jev")
        return Decision(
            {"true": float(fallback), "false": 1 - float(fallback)}, source="fallback"
        )

    def score(
        self,
        state: Any,
        criteria: List[str],
        instructions: str,
        fallback: Optional[Dict[str, float]] = None,
        key: str = "x",
    ) -> Decision:
        questions = {key: {"type": "score", "instructions": instructions, "criteria": criteria}}
        ans = self.client.decide(state, questions)
        entry = (ans or {}).get(key) or {}
        probs, conf = entry.get("probabilities"), entry.get("confidence")
        if probs:
            labeled = {criteria[int(i)]: v for i, v in probs.items() if int(i) < len(criteria)}
            return Decision(labeled, confidence=conf, source="jev", fallback=fallback)
        return Decision(None, source="fallback", fallback=fallback or _uniform(criteria))
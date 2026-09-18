"""Fail-open Jev client — TypeSafe "System One" decisions via OpenRouter.

Jev does not generate text: it evaluates typed *questions* against a *state*
and returns calibrated probabilities (``noul`` / ``choice`` / ``score``). This
module is a self-contained, fail-open wrapper for Veltiosi (no dependency on
the Edoras package). It NEVER raises: on any failure it returns ``None`` so the
classification path degrades to the deterministic keyword classifier.

Jev is ADVISORY in Veltiosi. It is never the sole arbiter of a classification —
the deterministic keyword classifier remains the floor, and low-confidence
answers escalate to review.

Environment:
    VELTIOSI_JEV_API_KEY  — override; falls back to OPENROUTER_API_KEY
    OPENROUTER_API_KEY    — required; absent => client disabled (no-op)
    VELTIOSI_JEV_ENABLED  — "0"/"false"/"off" disables even with a key (default on)
    VELTIOSI_JEV_MODEL    — model slug (default "~typesafe/jev-latest")
    VELTIOSI_JEV_BASE_URL — decisions endpoint (default OpenRouter alpha decisions)
    VELTIOSI_JEV_TIMEOUT  — per-call seconds (default 15)
"""

import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import requests  # noqa: F401 — guarded import; absence degrades to None (fail-open)
except Exception:  # pragma: no cover - requests is a declared dependency
    requests = None  # type: ignore[assignment]

DEFAULT_MODEL = "~typesafe/jev-latest"
DEFAULT_BASE_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_TIMEOUT = 15.0


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


class JevClient:
    """Thin, fail-open wrapper around the Jev Decisions API.

    ``decide()`` returns ``None`` (never raises) when disabled or on any
    transport / HTTP / parse failure, so callers treat Jev as an optional
    enrichment — exactly the fail-open contract Veltiosi requires.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.getenv("VELTIOSI_JEV_API_KEY") or os.getenv("OPENROUTER_API_KEY")

        self.model = model or os.getenv("VELTIOSI_JEV_MODEL") or DEFAULT_MODEL
        self.base_url = base_url or os.getenv("VELTIOSI_JEV_BASE_URL") or DEFAULT_BASE_URL

        if timeout is not None:
            self.timeout = float(timeout)
        else:
            try:
                self.timeout = float(os.getenv("VELTIOSI_JEV_TIMEOUT", DEFAULT_TIMEOUT))
            except (TypeError, ValueError):
                self.timeout = DEFAULT_TIMEOUT

        if enabled is None:
            enabled = _env_bool("VELTIOSI_JEV_ENABLED", True)
        self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        """True only when enabled by flag AND a key is present."""
        return self._enabled and bool(self.api_key)

    def decide(self, state: Any, questions: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate ``questions`` against ``state``; return the ``answers`` dict.

        ``state`` may be a str, dict, or list (passed through verbatim).
        ``questions`` is ``{name: {type, instructions, criteria?}}`` where type
        is one of ``noul`` | ``choice`` | ``score``.

        Returns ``None`` (never raises) when disabled or on any transport/parse
        failure, so callers treat Jev as an optional enrichment.
        """
        if not self.enabled:
            logger.debug("JevClient: disabled (no key or VELTIOSI_JEV_ENABLED=0)")
            return None

        payload = {"model": self.model, "state": state, "questions": questions}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if requests is None:
            logger.warning("JevClient: 'requests' unavailable — degrading to None")
            return None

        t0 = time.monotonic()
        try:
            resp = requests.post(
                self.base_url, headers=headers, json=payload, timeout=self.timeout
            )
        except Exception as e:  # noqa: BLE001 — fail-open, log-and-degrade
            logger.warning(
                f"JevClient: request failed after {time.monotonic() - t0:.2f}s — {e}"
            )
            return None

        elapsed = time.monotonic() - t0
        if resp.status_code != 200:
            snippet = (resp.text or "")[:200].replace("\n", " ")
            logger.warning(f"JevClient: HTTP {resp.status_code} in {elapsed:.2f}s — {snippet}")
            return None

        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"JevClient: non-JSON response — {e}")
            return None

        answers = data.get("answers")
        if not isinstance(answers, dict):
            logger.warning("JevClient: response missing 'answers' object")
            return None

        logger.info(
            f"JevClient: {self.model} answered {len(answers)} question(s) in {elapsed:.2f}s"
        )
        return answers
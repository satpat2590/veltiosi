"""Fail-open Jev client — TypeSafe "System One" decisions.

Jev does not generate text: it evaluates typed *questions* against a *state*
and returns calibrated probabilities (``noul`` / ``choice`` / ``score``). This
module is a self-contained, fail-open wrapper for Veltiosi (no dependency on
the Edoras package). It NEVER raises: on any failure it returns ``None`` so the
classification path degrades to the deterministic keyword classifier.

Jev is ADVISORY in Veltiosi. It is never the sole arbiter of a classification —
the deterministic keyword classifier remains the floor, and low-confidence
answers escalate to review.

Providers (tried in order; the first that yields answers wins):
    native     → POST https://api.typesafe.ai/v1/systemone         model "jev-latest"
    openrouter → POST https://openrouter.ai/api/alpha/decisions     model "~typesafe/jev-latest"

Environment:
    VELTIOSI_JEV_PROVIDER — comma-separated provider order; default "native,openrouter"
    VELTIOSI_JEV_API_KEY  — explicit key override (any provider)
    TYPESAFE_API_KEY      — used by the native provider (and no override)
    OPENROUTER_API_KEY    — used by the openrouter provider (and no override)
    VELTIOSI_JEV_ENABLED  — "0"/"false"/"off" disables even with a key (default on)
    VELTIOSI_JEV_MODEL    — model slug override (applies to primary provider)
    VELTIOSI_JEV_BASE_URL — decisions endpoint override (applies to primary provider)
    VELTIOSI_JEV_TIMEOUT  — per-call seconds (default 15)
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import requests  # noqa: F401 — guarded import; absence degrades to None (fail-open)
except Exception:  # pragma: no cover - requests is a declared dependency
    requests = None  # type: ignore[assignment]

DEFAULT_MODEL = "~typesafe/jev-latest"
DEFAULT_BASE_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_NATIVE_MODEL = "jev-latest"
DEFAULT_NATIVE_BASE_URL = "https://api.typesafe.ai/v1/systemone"
PROVIDERS = ("native", "openrouter")
DEFAULT_PROVIDER_ORDER = "native,openrouter"
DEFAULT_TIMEOUT = 15.0


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def _provider_key(provider: str) -> Optional[str]:
    if provider == "native":
        return os.getenv("VELTIOSI_JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY")
    return os.getenv("VELTIOSI_JEV_API_KEY") or os.getenv("OPENROUTER_API_KEY")


def _provider_model(provider: str) -> str:
    if provider == "native":
        return os.getenv("VELTIOSI_JEV_MODEL") or DEFAULT_NATIVE_MODEL
    return os.getenv("VELTIOSI_JEV_MODEL") or DEFAULT_MODEL


def _provider_base_url(provider: str) -> str:
    if provider == "native":
        return os.getenv("VELTIOSI_JEV_BASE_URL") or DEFAULT_NATIVE_BASE_URL
    return os.getenv("VELTIOSI_JEV_BASE_URL") or DEFAULT_BASE_URL


class JevClient:
    """Thin, fail-open wrapper around the Jev Decisions API.

    ``decide()`` returns ``None`` (never raises) when disabled or on any
    transport / HTTP / parse failure, so callers treat Jev as an optional
    enrichment — exactly the fail-open contract Veltiosi requires. Tries
    providers in order; the first valid ``answers`` dict wins.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        enabled: Optional[bool] = None,
        provider: Optional[str] = None,
    ) -> None:
        raw = (
            provider or os.getenv("VELTIOSI_JEV_PROVIDER") or DEFAULT_PROVIDER_ORDER
        ).strip().lower()
        order = [p for p in (x.strip() for x in raw.split(",")) if p in PROVIDERS]
        if not order:
            order = [p for p in DEFAULT_PROVIDER_ORDER.split(",") if p in PROVIDERS]
        self.provider = order[0]
        self._order = order

        chain: List[Tuple[Optional[str], str, str]] = []
        for i, p in enumerate(order):
            if i == 0:
                key = api_key if api_key is not None else _provider_key(p)
                m = model if model is not None else _provider_model(p)
                u = base_url if base_url is not None else _provider_base_url(p)
            else:
                key = _provider_key(p)
                m = _provider_model(p)
                u = _provider_base_url(p)
            chain.append((key, m, u))

        self._chain = chain
        self.api_key, self.model, self.base_url = chain[0]

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

        self.last_model: Optional[str] = None
        self.last_provider: Optional[str] = None

    @property
    def enabled(self) -> bool:
        """True only when enabled by flag AND at least one provider has a key."""
        return self._enabled and any(key for key, _, _ in self._chain)

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

        if requests is None:
            logger.warning("JevClient: 'requests' unavailable — degrading to None")
            return None

        for i, (key, model, base_url) in enumerate(self._chain):
            if not key:
                continue
            name = self._order[i]
            payload = {"model": model, "state": state, "questions": questions}
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }

            t0 = time.monotonic()
            try:
                resp = requests.post(base_url, headers=headers, json=payload, timeout=self.timeout)
            except Exception as e:  # noqa: BLE001 — try the next provider
                logger.warning(
                    f"JevClient[{name}]: request failed after {time.monotonic() - t0:.2f}s — {e}"
                )
                continue

            elapsed = time.monotonic() - t0
            if resp.status_code != 200:
                snippet = (resp.text or "")[:200].replace("\n", " ")
                logger.warning(f"JevClient[{name}]: HTTP {resp.status_code} in {elapsed:.2f}s — {snippet}")
                continue

            try:
                data = resp.json()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"JevClient[{name}]: non-JSON response — {e}")
                continue

            answers = data.get("answers")
            if not isinstance(answers, dict):
                logger.warning(f"JevClient[{name}]: response missing 'answers' object")
                continue

            self.last_model = data.get("model")
            self.last_provider = name

            logger.info(
                f"JevClient[{name}]: {self.last_model or model} answered {len(answers)} question(s) in {elapsed:.2f}s"
            )
            return answers

        logger.warning(f"JevClient: all providers failed ({', '.join(self._order)})")
        return None

"""Search everything across Omni — fast, ranked, no LLM in the loop.

Embed the query, cosine-rank the vault (fast search), and optionally Jev
re-rank the shortlist. Live sources (whoop/edoras/raga/itihasa/atma) are fetched
only when the query names them explicitly. No synthesis — just ranked results.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .semantic_search import get_index

logger = logging.getLogger(__name__)

_router: Optional[Any] = None

VAULT = Path.home() / "Obsidian"


def _get_router():
    global _router
    if _router is None:
        from ..indexing.jev_router import JevQueryRouter

        _router = JevQueryRouter()
    return _router


# Explicit live-source triggers — deterministic, never guessed.
SOURCE_KEYWORDS: Dict[str, tuple] = {
    "whoop": ("recovery", "strain", "sleep", "hrv", "heart rate", "resting", "spo2", "workout"),
    "edoras": ("portfolio", "nav", "trade", "position", "sharpe", "drawdown", "pnl", "return", "allocation"),
    "raga": ("listen", "spotify", "track", "song", "music", "playlist", "played"),
    "itihasa": ("history", "historical", "empire", "ancient", "medieval", "dynasty", "civilization", "bce"),
    "atma": ("task", "todo", "skill tree", "points", "completed", "due"),
}


def _live_source(q: str) -> Optional[str]:
    ql = q.lower()
    for source, keywords in SOURCE_KEYWORDS.items():
        if any(k in ql for k in keywords):
            return source
    return None


def search_everything(
    query: str, top_k: int = 15, fast_k: int = 50, rerank: bool = False
) -> Dict[str, Any]:
    index = get_index()
    candidates = index.search(query, k=fast_k)

    did_rerank = False
    if rerank and candidates:
        router = _get_router()
        items = [
            {"id": c["path"], "title": c["title"], "snippet": index.snippet(c["path"])}
            for c in candidates
        ]
        ranked = router.rerank(query, items, top_k=top_k)
        notes = [
            {"title": r["title"], "path": r["id"], "score": r["jscore"], "snippet": r["snippet"]}
            for r in ranked
        ]
        did_rerank = True
    else:
        notes = [
            {"title": c["title"], "path": c["path"], "score": c["score"], "snippet": index.snippet(c["path"])}
            for c in candidates[:top_k]
        ]

    source = _live_source(query)
    source_text = None
    if source:
        from ..connectors.datasources import query_source

        source_text = query_source(source, query)

    return {
        "query": query,
        "notes": notes,
        "source": source,
        "source_text": source_text,
        "reranked": did_rerank,
    }


def read_note(path: str) -> Optional[Dict[str, str]]:
    """Read a note's full content (title + body), restricted to the vault."""
    try:
        p = Path(path)
    except Exception:
        return None
    if not p.is_relative_to(VAULT) or not p.exists() or p.suffix != ".md":
        return None
    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        return None
    return {"title": p.stem, "path": str(p), "content": content}
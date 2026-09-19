"""Search everything across Omni — semantic, Jev-reranked, synthesized.

Two-step search (TypeSafe's pattern): embed queries + notes (fast search), then
Jev ``Noul`` re-rank each candidate ("does this answer the query?"), then Gemini
synthesizes a grounded answer. Live sources (whoop/edoras/raga/itihasa/atma) are
fetched only when the query names them explicitly — never guessed.
"""

import logging
from typing import Any, Dict, List, Optional

from .semantic_search import get_index
from ..indexing.jev_router import JevQueryRouter
from .llm_service import llm_service

logger = logging.getLogger(__name__)

_router: Optional[JevQueryRouter] = None


def _get_router() -> JevQueryRouter:
    global _router
    if _router is None:
        _router = JevQueryRouter()
    return _router


# Explicit live-source triggers. Deterministic on purpose: the previous build
# let Jev guess the source and it misrouted "paisa analysis" -> edoras. A live
# source is only touched when the query names its domain vocabulary.
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


def search_everything(query: str, top_k: int = 8, fast_k: int = 30) -> Dict[str, Any]:
    index = get_index()
    router = _get_router()

    # 1. fast search — embed query, cosine against the vault index
    candidates = index.search(query, k=fast_k)

    # 2. Jev re-rank — one fan-out Noul per candidate, sort by "answers the query?"
    route = router.route(query)
    reranked: List[Dict[str, Any]] = []
    if candidates:
        items = [
            {"id": c["path"], "title": c["title"], "snippet": index.snippet(c["path"])}
            for c in candidates
        ]
        reranked = router.rerank(query, items, top_k=top_k)

    notes = [
        {"title": r["title"], "path": r["id"], "score": r["jscore"], "snippet": r["snippet"]}
        for r in reranked
    ]

    # 3. live-source enrichment — only when the query names the source
    source = _live_source(query)
    source_text = None
    if source:
        from ..connectors.datasources import query_source

        source_text = query_source(source, query)

    # 4. synthesize a grounded answer (Gemini via OpenRouter)
    answer, citations = None, []
    if notes:
        context = "\n\n".join(
            f"--- Document {i + 1}: [[{n['title']}]] ---\n{n['snippet']}"
            for i, n in enumerate(notes)
        )
        if source_text:
            context += f"\n\n--- Live data ({source}) ---\n{source_text}"
        result = llm_service.generate_query_answer(question=query, wiki_context=context)
        if result:
            answer = result.answer
            citations = result.citations

    return {
        "query": query,
        "route": {
            "intent": route.intent,
            "domain": route.domain,
            "secondary_domains": route.secondary_domains,
        },
        "source": source,
        "notes": notes,
        "answer": answer,
        "citations": citations,
    }
"""Embedding-based fast search over the vault (step 1 of two-step search).

Per TypeSafe's re-ranking pattern: a cheap fast search (dense MiniLM embeddings)
cuts the whole vault to a shortlist, then Jev re-ranks the shortlist. This module
only does the fast search; `jev_router.rerank` is step 2. Embeddings are cached
to disk so the ~1200-note index is built once.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

VAULT = Path.home() / "Obsidian"
CACHE_DIR = Path.home() / ".cache" / "veltiosi"
VECTORS_PATH = CACHE_DIR / "note_vectors.npy"
MANIFEST_PATH = CACHE_DIR / "note_manifest.json"

IGNORED = {".git", ".obsidian", ".smart-env", ".trash"}


class SemanticIndex:
    def __init__(self, vault: Path = VAULT):
        self.vault = vault
        self.model = None
        self.kind = None
        self.paths: List[str] = []
        self.titles: List[str] = []
        self.vectors: Optional[np.ndarray] = None

    def _scan(self) -> List[Tuple[str, str, str]]:
        notes = []
        for p in sorted(self.vault.rglob("*.md")):
            if any(seg in IGNORED for seg in p.parts):
                continue
            try:
                content = p.read_text(encoding="utf-8")
            except Exception:
                continue
            notes.append((str(p), p.stem, p.stem + "\n" + content[:600]))
        return notes

    def build(self, force: bool = False) -> int:
        if not force and VECTORS_PATH.exists() and MANIFEST_PATH.exists():
            self.load()
            return len(self.paths)

        notes = self._scan()
        if not notes:
            logger.warning("no notes found in vault")
            return 0
        self.paths = [n[0] for n in notes]
        self.titles = [n[1] for n in notes]
        texts = [n[2] for n in notes]

        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            self.kind = "embeddings"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"sentence-transformers unavailable ({e}); using TFIDF")
            self.kind = "tfidf"

        t0 = time.time()
        if self.kind == "embeddings":
            self.vectors = self.model.encode(
                texts, show_progress_bar=False, normalize_embeddings=True
            ).astype(np.float32)
        else:
            from sklearn.feature_extraction.text import TfidfVectorizer

            tfidf = TfidfVectorizer(max_features=384, stop_words="english")
            self.vectors = tfidf.fit_transform(texts).toarray().astype(np.float32)
            self._tfidf = tfidf

        logger.info(f"embedded {len(notes)} notes in {time.time() - t0:.1f}s ({self.kind})")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(VECTORS_PATH, self.vectors)
        MANIFEST_PATH.write_text(
            json.dumps({"paths": self.paths, "titles": self.titles, "kind": self.kind})
        )
        return len(self.paths)

    def load(self) -> bool:
        if not VECTORS_PATH.exists() or not MANIFEST_PATH.exists():
            return False
        try:
            self.vectors = np.load(VECTORS_PATH)
            m = json.loads(MANIFEST_PATH.read_text())
            self.paths, self.titles, self.kind = m["paths"], m["titles"], m["kind"]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"failed to load index: {e}")
            return False
        if self.kind == "embeddings":
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                self.model = None
        return True

    def ready(self) -> bool:
        return self.vectors is not None and len(self.paths) > 0

    def _embed_query(self, query: str) -> np.ndarray:
        if self.kind == "embeddings" and self.model is not None:
            return self.model.encode([query], normalize_embeddings=True)[0].astype(np.float32)
        from sklearn.feature_extraction.text import TfidfVectorizer

        tfidf = TfidfVectorizer(max_features=384, stop_words="english")
        tfidf.fit([f"{t}" for t in self.titles])
        return tfidf.transform([query]).toarray().astype(np.float32)[0]

    def search(self, query: str, k: int = 30) -> List[dict]:
        if not self.ready():
            return []
        qv = self._embed_query(query)
        sims = self.vectors @ qv  # vectors are normalized => dot = cosine
        idx = np.argsort(-sims)[:k]
        out = []
        for i in idx:
            out.append({"path": self.paths[i], "title": self.titles[i], "score": float(sims[i])})
        return out

    def snippet(self, path: str, limit: int = 400) -> str:
        try:
            return Path(path).read_text(encoding="utf-8")[:limit]
        except Exception:
            return ""


_index: Optional[SemanticIndex] = None


def get_index() -> SemanticIndex:
    global _index
    if _index is None:
        _index = SemanticIndex()
        n = _index.build()
        logger.info(f"semantic index ready with {n} notes")
    return _index
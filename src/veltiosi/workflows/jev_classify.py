"""Jev classification workflow — batch-run the calibrated classifier.

Read-only: this produces an analysis (confidence distribution, deterministic-vs-
Jev disagreement, and a low-confidence review list). It never mutates the vault.
"""

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..indexing.jev_classifier import JevNoteClassifier
from ..indexing.scanner import VaultScanner
from ..models import NoteRecord

logger = logging.getLogger(__name__)


def _read_content(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — a missing/failed read must not sink the batch
        return ""


def _classify_one(classifier: JevNoteClassifier, note: NoteRecord) -> Dict[str, Any]:
    content = _read_content(note.path)
    result = classifier.classify(note.title, content)
    deterministic_root = (
        note.primary_root_category.value if note.primary_root_category else None
    )
    return {
        "path": str(note.path),
        "title": note.title,
        "domain_folder": note.domain_folder,
        "deterministic_root": deterministic_root,
        "deterministic_subcategories": list(note.subcategories),
        "available": result.available,
        "source": result.source,
        "root": result.root,
        "root_confidence": result.root_confidence,
        "root_probabilities": result.root_probabilities,
        "note_type": result.note_type,
        "note_type_confidence": result.note_type_confidence,
        "requires_slope": result.requires_slope,
        "cross_domain": result.cross_domain,
        "subcategories": result.subcategories,
        "subcategory_probs": result.subcategory_probs,
    }


def run_jev_classify(
    folder: Optional[str] = None,
    limit: Optional[int] = None,
    threshold: float = 0.55,
    workers: int = 16,
) -> Dict[str, Any]:
    """Scan (optionally a folder) and classify every note with Jev.

    Returns a summary dict plus per-note ``results`` (sorted by path) and a
    ``review`` list of low-confidence / unavailable notes.
    """
    scanner = VaultScanner()
    if folder:
        notes = scanner.scan_domain_folder(folder, limit=limit)
    else:
        notes = scanner.scan_vault(limit=limit)

    if not notes:
        return {"classified": 0, "available": 0, "notes": []}

    classifier = JevNoteClassifier()
    if not classifier.enabled:
        return {
            "classified": 0,
            "available": 0,
            "error": "Jev disabled (no OPENROUTER_API_KEY / VELTIOSI_JEV_API_KEY)",
            "notes": [],
        }

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_classify_one, classifier, note) for note in notes]
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:  # noqa: BLE001 — one bad note must not kill the batch
                logger.error(f"Jev classify failed: {e}")

    results.sort(key=lambda r: r["path"])

    available = [r for r in results if r["available"]]
    confident = [
        r
        for r in available
        if r["root_confidence"] is not None and r["root_confidence"] >= threshold
    ]
    review = [
        r
        for r in results
        if not r["available"]
        or r["root_confidence"] is None
        or r["root_confidence"] < threshold
    ]

    root_distribution = Counter(r["root"] for r in available if r["root"])
    det_root_distribution = Counter(
        r["deterministic_root"] for r in results if r["deterministic_root"]
    )

    disagreements = [
        r
        for r in available
        if r["deterministic_root"] is not None
        and r["root"] not in (None, "uncertain")
        and r["root"] != r["deterministic_root"]
    ]

    return {
        "classified": len(results),
        "available": len(available),
        "confident_root": len(confident),
        "threshold": threshold,
        "review_count": len(review),
        "root_distribution": dict(root_distribution),
        "deterministic_root_distribution": dict(det_root_distribution),
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "review": review,
        "results": results,
    }
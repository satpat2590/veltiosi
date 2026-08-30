"""Retrieval service for finding relevant notes."""

import logging
import re
from typing import Dict, List, Optional, Tuple

from ..models import NoteRecord, RootCategory
from ..services.wiki_repository import WikiRepository
from ..utils.text import extract_keywords, calculate_similarity, find_best_match

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for retrieving relevant notes for queries and context."""

    def __init__(self, repository: Optional[WikiRepository] = None):
        """Initialize retrieval service."""
        self.repository = repository or WikiRepository()
        logger.info("Retrieval service initialized")

    def retrieve_for_query(
        self,
        query: str,
        category_filter: Optional[RootCategory] = None,
        max_notes: int = 10,
        min_similarity: float = 0.3,
    ) -> List[NoteRecord]:
        """Retrieve notes relevant to a query."""
        notes = self.repository.scan_and_classify()

        if not notes:
            logger.warning("No notes found in vault")
            return []

        # Extract keywords from query
        query_keywords = set(extract_keywords(query, max_keywords=20))

        # Score each note
        scored_notes = []
        for note in notes:
            # Apply category filter
            if category_filter and note.primary_root_category != category_filter:
                continue

            score = self._calculate_relevance_score(note, query, query_keywords)
            if score >= min_similarity:
                scored_notes.append((note, score))

        # Sort by score (descending)
        scored_notes.sort(key=lambda x: x[1], reverse=True)

        # Return top notes
        result = [note for note, score in scored_notes[:max_notes]]
        logger.info(f"Retrieved {len(result)} notes for query: '{query[:50]}...'")
        return result

    def retrieve_for_source(
        self,
        source_title: str,
        source_content: str,
        source_type: Optional[str] = None,
        max_notes: int = 5,
    ) -> List[NoteRecord]:
        """Retrieve notes relevant to a source being ingested."""
        notes = self.repository.scan_and_classify()

        if not notes:
            return []

        # Combine title and content for keyword extraction
        source_text = f"{source_title} {source_content[:5000]}"  # Limit content
        source_keywords = set(extract_keywords(source_text, max_keywords=30))

        # Score each note
        scored_notes = []
        for note in notes:
            score = self._calculate_source_relevance_score(
                note, source_text, source_keywords, source_type
            )
            scored_notes.append((note, score))

        # Sort by score (descending)
        scored_notes.sort(key=lambda x: x[1], reverse=True)

        # Return top notes
        return [note for note, score in scored_notes[:max_notes]]

    def retrieve_for_weekly_synthesis(
        self, week_start_date, week_end_date, max_notes_per_category: int = 3
    ) -> Dict[str, List[NoteRecord]]:
        """Retrieve notes for weekly synthesis."""
        notes = self.repository.scan_and_classify()

        # Group by category
        notes_by_category: Dict[str, List[NoteRecord]] = {
            "physical": [],
            "mental": [],
            "financial": [],
            "social": [],
        }

        for note in notes:
            if note.primary_root_category:
                category = note.primary_root_category.value
                if category in notes_by_category:
                    notes_by_category[category].append(note)

        # For each category, get most relevant notes (recently modified, with slope sections)
        result = {}
        for category, category_notes in notes_by_category.items():
            # Sort by modification date (most recent first)
            category_notes.sort(key=lambda n: n.modified_at or n.created_at, reverse=True)

            # Prioritize notes with slope sections
            with_slope = [n for n in category_notes if n.has_slope_section]
            without_slope = [n for n in category_notes if not n.has_slope_section]

            # Combine: slope notes first, then others
            selected = with_slope[:max_notes_per_category]
            remaining_slots = max_notes_per_category - len(selected)
            if remaining_slots > 0:
                selected.extend(without_slope[:remaining_slots])

            result[category] = selected

        return result

    def _calculate_relevance_score(
        self, note: NoteRecord, query: str, query_keywords: set
    ) -> float:
        """Calculate relevance score for a note against a query."""
        score = 0.0

        # 1. Title match (highest weight)
        title_score = calculate_similarity(query.lower(), note.title.lower())
        score += title_score * 0.4

        # 2. Keyword overlap with note content
        note_content = self.repository.read_note_content(str(note.path))
        if note_content:
            # Extract keywords from note content
            note_keywords = set(extract_keywords(note_content[:2000], max_keywords=20))

            # Calculate keyword overlap
            if query_keywords and note_keywords:
                overlap = len(query_keywords & note_keywords)
                total = len(query_keywords | note_keywords)
                keyword_score = overlap / total if total > 0 else 0
                score += keyword_score * 0.3

        # 3. Category match (if query mentions categories)
        if note.primary_root_category:
            category_terms = {
                "physical": {"health", "exercise", "body", "physical", "fitness"},
                "mental": {"mind", "mental", "learn", "study", "think", "research"},
                "financial": {"money", "finance", "trading", "investment", "economic"},
                "social": {"social", "relationship", "friend", "family", "community"},
            }

            category = note.primary_root_category.value
            if category in category_terms:
                category_words = category_terms[category]
                query_words = set(query.lower().split())
                category_overlap = len(category_words & query_words)
                if category_overlap > 0:
                    score += 0.2

        # 4. Backlink popularity (notes with many incoming links are more important)
        backlink_count = len(note.wikilinks_in)
        backlink_score = min(backlink_count / 10, 0.1)  # Cap at 0.1
        score += backlink_score

        return min(score, 1.0)  # Cap at 1.0

    def _calculate_source_relevance_score(
        self,
        note: NoteRecord,
        source_text: str,
        source_keywords: set,
        source_type: Optional[str] = None,
    ) -> float:
        """Calculate relevance score for a note against a source."""
        score = 0.0

        # Read note content
        note_content = self.repository.read_note_content(str(note.path))
        if not note_content:
            return 0.0

        # 1. Keyword overlap
        note_keywords = set(extract_keywords(note_content[:2000], max_keywords=20))
        if source_keywords and note_keywords:
            overlap = len(source_keywords & note_keywords)
            total = len(source_keywords | note_keywords)
            keyword_score = overlap / total if total > 0 else 0
            score += keyword_score * 0.5

        # 2. Note type relevance
        if source_type:
            # Source summaries should connect to other source summaries
            if note.note_type.value == "source_summary":
                score += 0.2

            # Research papers might connect to research frameworks
            if source_type == "paper" and note.note_type.value == "concept":
                if "research" in note.domain_folder.lower() or "research" in note_content.lower():
                    score += 0.1

        # 3. Domain folder relevance
        # Sources often relate to notes in the same domain
        if note.domain_folder != "root":
            # Check if domain folder appears in source text
            domain_terms = note.domain_folder.lower().replace("-", " ").split()
            source_lower = source_text.lower()
            domain_match = any(term in source_lower for term in domain_terms)
            if domain_match:
                score += 0.1

        # 4. Recency (more recent notes are more relevant)
        if note.modified_at:
            # Simple recency boost (notes modified in last 30 days get bonus)
            from datetime import datetime, timedelta

            thirty_days_ago = datetime.now() - timedelta(days=30)
            # Make both datetimes offset-naive for comparison
            note_time = (
                note.modified_at.replace(tzinfo=None)
                if note.modified_at.tzinfo
                else note.modified_at
            )
            if note_time > thirty_days_ago:
                score += 0.1

        return min(score, 1.0)

    def format_citations(self, notes: List[NoteRecord]) -> List[str]:
        """Format notes as citations."""
        citations = []
        for note in notes:
            # Use note title as citation
            citation = f"[[{note.title}]]"

            # Add domain folder context if available
            if note.domain_folder != "root":
                citation += f" ({note.domain_folder})"

            citations.append(citation)

        return citations

    def deduplicate_citations(self, citations: List[str]) -> List[str]:
        """Remove duplicate citations while preserving order."""
        seen = set()
        deduplicated = []
        for citation in citations:
            if citation not in seen:
                seen.add(citation)
                deduplicated.append(citation)
        return deduplicated

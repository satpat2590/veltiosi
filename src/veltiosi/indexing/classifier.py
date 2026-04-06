"""Note classifier for categorizing and enriching notes."""

import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from ..models import NoteRecord, RootCategory
from ..settings import settings
from ..utils.text import extract_keywords_set, calculate_similarity

logger = logging.getLogger(__name__)


class NoteClassifier:
    """Classifier for categorizing and enriching notes."""

    def __init__(self):
        """Initialize note classifier."""
        self.subcategory_keywords: Dict[str, Set[str]] = {}
        self._build_subcategory_keywords()

        # Category mapping cache
        self._category_cache: Dict[str, Tuple[Optional[str], List[str]]] = {}

        logger.info("Note classifier initialized")

    def _build_subcategory_keywords(self) -> None:
        """Build keyword sets for each subcategory."""
        for subcat_name, subcat_config in settings.subcategories.items():
            keywords = set()

            # Add display name words
            keywords.update(subcat_config.display_name.lower().split())

            # Add domain folder names
            for domain in subcat_config.domain_folders:
                keywords.update(domain.lower().replace("-", " ").split())

            # Add description words if available
            if subcat_config.description:
                keywords.update(subcat_config.description.lower().split())

            self.subcategory_keywords[subcat_name] = keywords

    def classify_note(
        self, note: NoteRecord, content: Optional[str] = None, force_reclassify: bool = False
    ) -> NoteRecord:
        """Classify a note, determining its categories and subcategories."""
        # Check cache if not forcing reclassification
        cache_key = str(note.path)
        if not force_reclassify and cache_key in self._category_cache:
            primary, subcats = self._category_cache[cache_key]
            note.primary_root_category = RootCategory(primary) if primary else None
            note.subcategories = subcats
            return note

        # Get note content if not provided
        if content is None:
            try:
                with open(note.path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"Failed to read content of {note.path}: {e}")
                content = ""

        # Extract keywords from title and content
        text_to_analyze = f"{note.title} {content[:5000]}"  # Limit content for performance
        keywords = extract_keywords_set(text_to_analyze)

        # Determine primary root category from domain folder
        primary_root = self._get_primary_root_from_domain(note.domain_folder)

        # Determine subcategories
        subcategories = self._get_subcategories_from_content(
            keywords=keywords, domain_folder=note.domain_folder, primary_root=primary_root
        )

        # If no subcategories found, try to infer from content
        if not subcategories and content:
            subcategories = self._infer_subcategories_from_content(content, primary_root)

        # Update note
        note.primary_root_category = primary_root
        note.subcategories = subcategories

        # Update cache
        self._category_cache[cache_key] = (
            primary_root.value if primary_root else None,
            subcategories,
        )

        return note

    def _get_primary_root_from_domain(self, domain_folder: str) -> Optional[RootCategory]:
        """Get primary root category from domain folder."""
        if domain_folder == "root":
            return None

        domain_config = settings.domain_folders.get(domain_folder)
        if domain_config and domain_config.default_roots:
            try:
                return RootCategory(domain_config.default_roots[0])
            except ValueError:
                logger.warning(
                    f"Invalid root category in domain config: {domain_config.default_roots[0]}"
                )

        return None

    def _get_subcategories_from_content(
        self, keywords: Set[str], domain_folder: str, primary_root: Optional[RootCategory]
    ) -> List[str]:
        """Get subcategories from content keywords."""
        subcategory_scores: Dict[str, float] = {}

        for subcat_name, subcat_keywords in self.subcategory_keywords.items():
            # Check if subcategory matches primary root
            subcat_config = settings.subcategories[subcat_name]
            if primary_root and subcat_config.primary_root != primary_root.value:
                continue

            # Calculate keyword overlap
            overlap = len(keywords.intersection(subcat_keywords))
            if overlap > 0:
                score = overlap / len(subcat_keywords)
                subcategory_scores[subcat_name] = score

        # Sort by score and take top matches
        sorted_subcats = sorted(subcategory_scores.items(), key=lambda x: x[1], reverse=True)

        # Return subcategories with score above threshold
        threshold = 0.3
        return [subcat for subcat, score in sorted_subcats if score >= threshold]

    def _infer_subcategories_from_content(
        self, content: str, primary_root: Optional[RootCategory]
    ) -> List[str]:
        """Infer subcategories from content using simple heuristics."""
        inferred = []
        content_lower = content.lower()

        # Health-related content
        health_terms = ["health", "wellness", "medical", "doctor", "hospital", "symptom"]
        if any(term in content_lower for term in health_terms):
            inferred.append("health")

        # Exercise-related content
        exercise_terms = ["exercise", "workout", "gym", "running", "yoga", "fitness"]
        if any(term in content_lower for term in exercise_terms):
            inferred.append("exercise")

        # Nutrition-related content
        nutrition_terms = ["food", "diet", "nutrition", "meal", "eating", "calorie"]
        if any(term in content_lower for term in nutrition_terms):
            inferred.append("nutrition")

        # Relationships content
        relationship_terms = ["friend", "relationship", "family", "partner", "social"]
        if any(term in content_lower for term in relationship_terms):
            inferred.append("relationships")

        # Language learning
        language_terms = ["language", "vocabulary", "grammar", "speak", "learn"]
        if any(term in content_lower for term in language_terms):
            inferred.append("language_learning")

        # Poetry
        poetry_terms = ["poem", "poetry", "verse", "rhyme", "meter"]
        if any(term in content_lower for term in poetry_terms):
            inferred.append("poetry")

        # Research
        research_terms = ["research", "study", "paper", "academic", "scholar"]
        if any(term in content_lower for term in research_terms):
            inferred.append("research")

        # Trading systems
        trading_terms = ["trade", "trading", "market", "stock", "investment"]
        if any(term in content_lower for term in trading_terms):
            inferred.append("trading_systems")

        # Data engineering
        data_terms = ["data", "database", "etl", "pipeline", "warehouse"]
        if any(term in content_lower for term in data_terms):
            inferred.append("data_engineering")

        # ML Ops
        ml_terms = ["machine learning", "ml", "model", "ai", "algorithm"]
        if any(term in content_lower for term in ml_terms):
            inferred.append("ml_ops")

        # Filter by primary root if specified
        if primary_root:
            filtered = []
            for subcat in inferred:
                subcat_config = settings.subcategories.get(subcat)
                if subcat_config and subcat_config.primary_root == primary_root.value:
                    filtered.append(subcat)
            return filtered

        return inferred

    def batch_classify(
        self, notes: List[NoteRecord], force_reclassify: bool = False
    ) -> List[NoteRecord]:
        """Batch classify multiple notes."""
        classified_notes = []

        for i, note in enumerate(notes):
            try:
                classified_note = self.classify_note(note, force_reclassify=force_reclassify)
                classified_notes.append(classified_note)
            except Exception as e:
                logger.error(f"Failed to classify note {note.path}: {e}")
                classified_notes.append(note)  # Keep original note

            if (i + 1) % 50 == 0:
                logger.info(f"Classified {i + 1} notes...")

        # Calculate classification statistics
        classified_count = sum(1 for n in classified_notes if n.primary_root_category)
        subcat_count = sum(len(n.subcategories) for n in classified_notes)

        logger.info(
            f"Classification complete: {classified_count}/{len(notes)} notes categorized, "
            f"{subcat_count} total subcategory assignments"
        )

        return classified_notes

    def get_classification_statistics(self, notes: List[NoteRecord]) -> Dict[str, any]:
        """Get statistics about note classifications."""
        from collections import Counter

        stats = {
            "total_notes": len(notes),
            "notes_with_primary_category": 0,
            "notes_with_subcategories": 0,
            "primary_category_distribution": Counter(),
            "subcategory_distribution": Counter(),
            "subcategories_per_note": [],
            "uncategorized_notes": [],
        }

        for note in notes:
            if note.primary_root_category:
                stats["notes_with_primary_category"] += 1
                stats["primary_category_distribution"][note.primary_root_category.value] += 1

            if note.subcategories:
                stats["notes_with_subcategories"] += 1
                stats["subcategories_per_note"].append(len(note.subcategories))
                for subcat in note.subcategories:
                    stats["subcategory_distribution"][subcat] += 1
            else:
                stats["uncategorized_notes"].append(str(note.path))

        if stats["subcategories_per_note"]:
            stats["avg_subcategories_per_note"] = sum(stats["subcategories_per_note"]) / len(
                stats["subcategories_per_note"]
            )
        else:
            stats["avg_subcategories_per_note"] = 0

        return stats

    def suggest_category_for_text(
        self, text: str, existing_categories: Optional[List[str]] = None
    ) -> Dict[str, any]:
        """Suggest categories for a piece of text."""
        keywords = extract_keywords_set(text)

        # Score each subcategory
        subcategory_scores: Dict[str, float] = {}
        for subcat_name, subcat_keywords in self.subcategory_keywords.items():
            overlap = len(keywords.intersection(subcat_keywords))
            if overlap > 0:
                score = overlap / len(subcat_keywords)
                subcategory_scores[subcat_name] = score

        # Get top suggestions
        sorted_suggestions = sorted(subcategory_scores.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]  # Top 5

        # Map to root categories
        suggestions = []
        for subcat, score in sorted_suggestions:
            subcat_config = settings.subcategories[subcat]
            suggestions.append(
                {
                    "subcategory": subcat,
                    "display_name": subcat_config.display_name,
                    "primary_root": subcat_config.primary_root,
                    "confidence": score,
                    "moc_path": subcat_config.moc_path,
                }
            )

        return {
            "suggestions": suggestions,
            "keywords_found": list(keywords)[:20],  # Top 20 keywords
        }

    def validate_classifications(self, notes: List[NoteRecord]) -> List[Dict[str, any]]:
        """Validate note classifications and return issues."""
        issues = []

        for note in notes:
            # Check if note has domain folder but no primary category
            if note.domain_folder != "root" and not note.primary_root_category:
                issues.append(
                    {
                        "type": "missing_primary_category",
                        "note_path": str(note.path),
                        "domain_folder": note.domain_folder,
                        "message": f"Note in domain folder '{note.domain_folder}' has no primary root category",
                    }
                )

            # Check if note has primary category but no subcategories
            if note.primary_root_category and not note.subcategories:
                issues.append(
                    {
                        "type": "missing_subcategories",
                        "note_path": str(note.path),
                        "primary_category": note.primary_root_category.value,
                        "message": f"Note with primary category '{note.primary_root_category.value}' has no subcategories",
                    }
                )

            # Check if subcategories match primary root
            for subcat in note.subcategories:
                subcat_config = settings.subcategories.get(subcat)
                if subcat_config and note.primary_root_category:
                    if subcat_config.primary_root != note.primary_root_category.value:
                        issues.append(
                            {
                                "type": "mismatched_subcategory",
                                "note_path": str(note.path),
                                "primary_category": note.primary_root_category.value,
                                "subcategory": subcat,
                                "subcategory_root": subcat_config.primary_root,
                                "message": f"Subcategory '{subcat}' (root: {subcat_config.primary_root}) doesn't match note's primary category '{note.primary_root_category.value}'",
                            }
                        )

        return issues

"""Text processing utilities for Veltiosi."""

import re
from typing import List, Optional, Set


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug.

    Args:
        text: Text to slugify

    Returns:
        Slugified text
    """
    # Convert to lowercase
    text = text.lower()

    # Replace spaces and underscores with hyphens
    text = re.sub(r"[_\s]+", "-", text)

    # Remove all non-alphanumeric characters except hyphens
    text = re.sub(r"[^a-z0-9\-]", "", text)

    # Remove leading/trailing hyphens
    text = text.strip("-")

    # Remove multiple consecutive hyphens
    text = re.sub(r"-+", "-", text)

    return text


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to a maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length (including suffix)
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    # Leave room for suffix
    truncate_length = max_length - len(suffix)
    if truncate_length <= 0:
        return suffix

    # Truncate at word boundary if possible
    truncated = text[:truncate_length]
    last_space = truncated.rfind(" ")
    if last_space > truncate_length * 0.7:  # Only if we're not cutting too much
        truncated = truncated[:last_space]

    return truncated.rstrip() + suffix


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """Extract keywords from text.

    Args:
        text: Text to extract keywords from
        max_keywords: Maximum number of keywords to return

    Returns:
        List of keywords
    """
    # Convert to lowercase
    text = text.lower()

    # Remove punctuation
    text = re.sub(r"[^\w\s]", " ", text)

    # Split into words
    words = text.split()

    # Remove stop words (simplified list)
    stop_words = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "should",
        "could",
        "can",
        "may",
        "might",
        "must",
        "shall",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "its",
        "our",
        "their",
        "mine",
        "yours",
        "hers",
        "ours",
        "theirs",
    }

    # Count word frequencies
    word_counts = {}
    for word in words:
        if word not in stop_words and len(word) > 2:
            word_counts[word] = word_counts.get(word, 0) + 1

    # Sort by frequency (descending)
    sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)

    # Return top keywords
    return [word for word, _ in sorted_words[:max_keywords]]


def find_best_match(query: str, candidates: List[str], threshold: float = 0.6) -> Optional[str]:
    """Find the best match for a query among candidates using simple string similarity.

    Args:
        query: Query string
        candidates: List of candidate strings
        threshold: Minimum similarity threshold (0-1)

    Returns:
        Best match or None if below threshold
    """
    if not candidates:
        return None

    query_lower = query.lower()
    best_match = None
    best_score = 0.0

    for candidate in candidates:
        candidate_lower = candidate.lower()

        # Simple similarity: check if query is substring of candidate or vice versa
        if query_lower in candidate_lower or candidate_lower in query_lower:
            score = len(query_lower) / max(len(candidate_lower), 1)
            if score > best_score:
                best_score = score
                best_match = candidate
        else:
            # Check word overlap
            query_words = set(query_lower.split())
            candidate_words = set(candidate_lower.split())
            if query_words and candidate_words:
                overlap = len(query_words & candidate_words)
                total = len(query_words | candidate_words)
                score = overlap / total if total > 0 else 0
                if score > best_score:
                    best_score = score
                    best_match = candidate

    return best_match if best_score >= threshold else None


def normalize_text(text: str) -> str:
    """Normalize text for comparison.

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    # Convert to lowercase
    text = text.lower()

    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)

    # Remove punctuation (keep basic separators)
    text = re.sub(r"[^\w\s\-]", "", text)

    return text.strip()


def extract_quoted_strings(text: str) -> List[str]:
    """Extract quoted strings from text.

    Args:
        text: Text to extract from

    Returns:
        List of quoted strings
    """
    # Match both single and double quotes
    pattern = r'["\']([^"\']*)["\']'
    return re.findall(pattern, text)


def wrap_text(text: str, width: int = 80) -> str:
    """Wrap text to specified width.

    Args:
        text: Text to wrap
        width: Maximum line width

    Returns:
        Wrapped text
    """
    lines = []
    current_line = []
    current_length = 0

    for word in text.split():
        word_length = len(word)

        if current_length + word_length + (1 if current_line else 0) <= width:
            current_line.append(word)
            current_length += word_length + (1 if current_line else 0)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_length = word_length

    if current_line:
        lines.append(" ".join(current_line))

    return "\n".join(lines)


def count_words(text: str) -> int:
    """Count words in text.

    Args:
        text: Text to count

    Returns:
        Word count
    """
    # Split on whitespace and filter out empty strings
    words = [word for word in text.split() if word.strip()]
    return len(words)


def extract_hashtags(text: str) -> List[str]:
    """Extract hashtags from text.

    Args:
        text: Text to extract from

    Returns:
        List of hashtags (without #)
    """
    pattern = r"#(\w+)"
    return re.findall(pattern, text)


def clean_html_tags(text: str) -> str:
    """Remove HTML tags from text.

    Args:
        text: Text with possible HTML tags

    Returns:
        Clean text
    """
    return re.sub(r"<[^>]+>", "", text)


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two texts using Jaccard similarity.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity score between 0 and 1
    """
    # Normalize texts
    text1_normalized = normalize_text(text1)
    text2_normalized = normalize_text(text2)

    # Split into words
    words1 = set(text1_normalized.split())
    words2 = set(text2_normalized.split())

    # Calculate Jaccard similarity
    if not words1 and not words2:
        return 1.0  # Both empty
    elif not words1 or not words2:
        return 0.0  # One empty

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union


def extract_keywords_set(text: str, max_keywords: int = 20) -> Set[str]:
    """Extract keywords as a set (for classifier use).

    Args:
        text: Text to extract keywords from
        max_keywords: Maximum number of keywords

    Returns:
        Set of keywords
    """
    keywords = extract_keywords(text, max_keywords)
    return set(keywords)

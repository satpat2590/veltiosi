"""Source loader service for ingesting external content."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..models import SourceRecord
from ..utils.ids import generate_hash_id

logger = logging.getLogger(__name__)


class SourceLoader:
    """Service for loading and processing external sources."""

    def __init__(self):
        """Initialize source loader."""
        logger.info("Source loader initialized")

    def load_source(
        self, source_location: str, source_type: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Load a source from a file path or URL."""
        # Determine if it's a URL or file path
        if self._is_url(source_location):
            return self._load_from_url(source_location, source_type)
        else:
            return self._load_from_file(source_location, source_type)

    def _is_url(self, location: str) -> bool:
        """Check if location is a URL."""
        try:
            result = urlparse(location)
            return all([result.scheme, result.netloc])
        except:
            return False

    def _load_from_file(
        self, file_path: str, source_type: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Load source from a local file."""
        try:
            path = Path(file_path).expanduser()
            if not path.exists():
                logger.error(f"Source file not found: {file_path}")
                return None, None

            # Read file content
            content = path.read_text(encoding="utf-8", errors="ignore")

            # Determine source type from extension if not provided
            if not source_type:
                source_type = self._infer_source_type_from_path(path)

            # Extract title from first line or filename
            title = self._extract_title_from_content(content, path.stem)

            # Generate source ID
            source_id = generate_hash_id(f"{title}{content[:1000]}")

            # Create source record
            logger.info(f"Loaded source from file: {title} ({source_type})")
            return content, title

        except Exception as e:
            logger.error(f"Failed to load source from file {file_path}: {e}")
            return None, None

    def _load_from_url(
        self, url: str, source_type: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Load source from a URL."""
        try:
            # Fetch URL content
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, "html.parser")

            # Extract title
            title = self._extract_title_from_html(soup, url)

            # Extract main content
            content = self._extract_content_from_html(soup)

            # Determine source type if not provided
            if not source_type:
                source_type = self._infer_source_type_from_url(url, soup)

            # Generate source ID
            source_id = generate_hash_id(f"{title}{content[:1000]}")

            logger.info(f"Loaded source from URL: {title} ({source_type})")
            return content, title

        except Exception as e:
            logger.error(f"Failed to load source from URL {url}: {e}")
            return None, None

    def _infer_source_type_from_path(self, path: Path) -> str:
        """Infer source type from file path."""
        extension = path.suffix.lower()

        type_map = {
            ".pdf": "paper",
            ".md": "article",
            ".txt": "article",
            ".doc": "document",
            ".docx": "document",
            ".csv": "data",
            ".json": "data",
            ".yaml": "data",
            ".yml": "data",
        }

        return type_map.get(extension, "article")

    def _infer_source_type_from_url(self, url: str, soup: BeautifulSoup) -> str:
        """Infer source type from URL and HTML."""
        url_lower = url.lower()

        # Check URL patterns
        if "arxiv.org" in url_lower or "doi.org" in url_lower:
            return "paper"
        elif "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "video"
        elif "spotify.com" in url_lower or "podcast" in url_lower:
            return "podcast"
        elif "github.com" in url_lower:
            return "code"

        # Check HTML meta tags
        meta_tags = soup.find_all("meta")
        for tag in meta_tags:
            property_attr = tag.get("property", "").lower()
            content_attr = tag.get("content", "").lower()

            if "article" in property_attr or "article" in content_attr:
                return "article"
            elif "book" in property_attr or "book" in content_attr:
                return "book"
            elif "video" in property_attr or "video" in content_attr:
                return "video"

        # Default to article
        return "article"

    def _extract_title_from_content(self, content: str, fallback: str) -> str:
        """Extract title from file content."""
        # Try to find first heading
        lines = content.split("\n")
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            elif line.startswith("## "):
                return line[3:].strip()

        # Use filename as fallback
        return fallback.replace("_", " ").replace("-", " ").title()

    def _extract_title_from_html(self, soup: BeautifulSoup, url: str) -> str:
        """Extract title from HTML."""
        # Try <title> tag
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
            if title and len(title) > 5:
                return title

        # Try OpenGraph or Twitter meta tags
        meta_tags = [
            ("meta", {"property": "og:title"}),
            ("meta", {"name": "twitter:title"}),
            ("meta", {"name": "title"}),
        ]

        for tag_name, attrs in meta_tags:
            tag = soup.find(tag_name, attrs)
            if tag and tag.get("content"):
                title = tag["content"].strip()
                if title and len(title) > 5:
                    return title

        # Try <h1> tags
        h1_tags = soup.find_all("h1")
        for h1 in h1_tags[:3]:  # Check first 3 h1 tags
            if h1.string:
                title = h1.string.strip()
                if title and len(title) > 5:
                    return title

        # Use URL as last resort
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path:
            # Clean up path to create title
            title = path.split("/")[-1].replace("-", " ").replace("_", " ").title()
            return title

        return "Untitled Source"

    def _extract_content_from_html(self, soup: BeautifulSoup) -> str:
        """Extract main content from HTML."""
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Try to find main content area
        main_selectors = [
            "article",
            "main",
            ".content",
            ".post-content",
            ".article-content",
            "#content",
            "#main",
        ]

        for selector in main_selectors:
            element = soup.select_one(selector)
            if element:
                # Get text with some formatting
                paragraphs = element.find_all(["p", "h1", "h2", "h3", "li"])
                text_parts = []
                for p in paragraphs[:50]:  # Limit to first 50 elements
                    text = p.get_text().strip()
                    if text and len(text) > 10:
                        text_parts.append(text)

                if text_parts:
                    return "\n\n".join(text_parts)

        # Fallback: get all text
        text = soup.get_text()

        # Clean up text
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line and len(line) > 20]

        return "\n\n".join(lines[:100])  # Limit to 100 paragraphs

    def sanitize_filename(self, title: str, max_length: int = 100) -> str:
        """Sanitize a title for use as a filename."""
        # Remove invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "", title)

        # Replace spaces with hyphens
        sanitized = re.sub(r"\s+", "-", sanitized)

        # Limit length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip("-")

        return sanitized

    def generate_summary_note_path(
        self,
        source_record: SourceRecord,
        domain_folder: Optional[str] = None,
        vault_path: Optional[Path] = None,
    ) -> Path:
        """Generate path for a source summary note."""
        from ..settings import settings

        vault_path = vault_path or settings.obsidian_vault

        # Determine target folder
        if domain_folder:
            target_folder = domain_folder
        else:
            # Use source type to determine folder
            type_to_folder = {
                "paper": "03-Academic-Papers",
                "article": "02-Articles",
                "book": "01-Books",
                "video": "09-Videos",
                "podcast": "10-Podcasts",
                "data": "11-Data",
                "receipt": "12-Receipts",
            }
            target_folder = type_to_folder.get(source_record.source_type, "17-References")

        # Sanitize title for filename
        filename = self.sanitize_filename(source_record.title)

        # Add date prefix if available
        if source_record.source_date:
            date_str = source_record.source_date.strftime("%Y-%m-%d")
            filename = f"{date_str} {filename}"

        # Add .md extension
        filename = f"{filename}.md"

        # Return full path
        return vault_path / target_folder / filename

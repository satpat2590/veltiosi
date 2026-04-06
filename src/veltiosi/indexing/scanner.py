"""Vault scanner for discovering and analyzing notes."""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models import NoteRecord, NoteType, GeneratedStatus
from ..settings import settings
from ..utils.dates import parse_date_from_filename, parse_date_from_content
from ..utils.markdown import extract_wikilinks, extract_frontmatter, has_slope_section

logger = logging.getLogger(__name__)


class VaultScanner:
    """Scanner for discovering and analyzing notes in the Obsidian vault."""

    def __init__(self, vault_path: Optional[Path] = None):
        """Initialize vault scanner."""
        self.vault_path = vault_path or settings.obsidian_vault
        self.ignored_paths = set(settings.generation_rules.ignored_paths)

        # Domain folder patterns (e.g., "01-Natural-Philosophy/", "20-Task-System/")
        self.domain_folders: Set[str] = set()
        self._discover_domain_folders()

        logger.info(f"Vault scanner initialized for: {self.vault_path}")
        logger.info(f"Found {len(self.domain_folders)} domain folders")

    def _discover_domain_folders(self) -> None:
        """Discover domain folders in the vault."""
        if not self.vault_path.exists():
            logger.warning(f"Vault path does not exist: {self.vault_path}")
            return

        for item in self.vault_path.iterdir():
            if item.is_dir():
                # Check if it matches domain folder pattern (e.g., "01-Natural-Philosophy")
                if re.match(r"^\d{2}-[A-Za-z-]+$", item.name):
                    self.domain_folders.add(item.name)

        # Also check for any configured domain folders that might not follow pattern
        for domain in settings.domain_folders.keys():
            domain_path = self.vault_path / domain
            if domain_path.exists() and domain_path.is_dir():
                self.domain_folders.add(domain)

    def _get_domain_folder_for_path(self, file_path: Path) -> Optional[str]:
        """Determine which domain folder a file belongs to."""
        # Get relative path from vault
        try:
            rel_path = file_path.relative_to(self.vault_path)
        except ValueError:
            return None

        # Check each path component
        for part in rel_path.parts:
            if part in self.domain_folders:
                return part

        # Check if file is in root of vault
        if len(rel_path.parts) == 1:
            return "root"

        return None

    def _classify_note_type(self, file_path: Path, content: str) -> NoteType:
        """Classify the type of note based on content and location."""
        # Check for MOC (Map of Content) patterns
        filename = file_path.stem.lower()
        if "moc" in filename or "index" in filename or "map" in filename:
            return NoteType.MOC

        # Check for generated index
        if "<!-- veltiosi:generated:start -->" in content:
            return NoteType.GENERATED_INDEX

        # Check for task-linked notes
        if "20-Task-System" in str(file_path):
            return NoteType.TASK_LINKED

        # Check for compounding pages (daily notes, weekly notes, etc.)
        if re.match(r"^\d{4}-\d{2}-\d{2}", filename) or "daily" in filename.lower():
            return NoteType.COMPOUNDING_PAGE

        # Check for source summaries
        frontmatter_tuple = extract_frontmatter(content)
        if frontmatter_tuple and frontmatter_tuple[0] and frontmatter_tuple[0].get("source_type"):
            return NoteType.SOURCE_SUMMARY

        # Check for synthesis notes
        if "synthesis" in filename.lower() or "weekly" in filename.lower():
            return NoteType.SYNTHESIS

        # Default to concept
        return NoteType.CONCEPT

    def _determine_generated_status(self, content: str) -> GeneratedStatus:
        """Determine if note is manual, generated, or mixed."""
        has_generated_marker = "<!-- veltiosi:generated:start -->" in content

        # Check if content has manual sections
        lines = content.split("\n")
        manual_sections = 0
        generated_sections = 0

        in_generated_section = False
        for line in lines:
            if "<!-- veltiosi:generated:start -->" in line:
                in_generated_section = True
                generated_sections += 1
            elif "<!-- veltiosi:generated:end -->" in line:
                in_generated_section = False
            elif not in_generated_section and line.strip() and not line.startswith("#"):
                manual_sections += 1

        if has_generated_marker and manual_sections > 0:
            return GeneratedStatus.MIXED
        elif has_generated_marker:
            return GeneratedStatus.GENERATED
        else:
            return GeneratedStatus.MANUAL

    def scan_note(self, file_path: Path) -> Optional[NoteRecord]:
        """Scan a single note file and extract metadata."""
        if not file_path.exists():
            logger.warning(f"Note file does not exist: {file_path}")
            return None

        # Check if path should be ignored
        rel_path = file_path.relative_to(self.vault_path)
        if any(ignored in str(rel_path) for ignored in self.ignored_paths):
            logger.debug(f"Ignoring note (in ignored paths): {rel_path}")
            return None

        try:
            # Read file content
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract basic metadata
            domain_folder = self._get_domain_folder_for_path(file_path)
            title = file_path.stem
            note_type = self._classify_note_type(file_path, content)
            generated_status = self._determine_generated_status(content)

            # Extract wikilinks
            wikilinks_out = extract_wikilinks(content)

            # Check for slope section
            has_slope = has_slope_section(content)

            # Get file stats
            stat = file_path.stat()
            created_at = parse_date_from_filename(file_path.name) or parse_date_from_content(
                content
            )

            # Determine categories based on domain folder
            primary_root_category = None
            secondary_root_categories = []
            subcategories = []

            if domain_folder and domain_folder != "root":
                domain_config = settings.domain_folders.get(domain_folder)
                if domain_config:
                    primary_root_category = (
                        domain_config.default_roots[0] if domain_config.default_roots else None
                    )
                    secondary_root_categories = (
                        domain_config.default_roots[1:]
                        if len(domain_config.default_roots) > 1
                        else []
                    )

                    # Map domain folder to subcategories
                    for subcat_name, subcat_config in settings.subcategories.items():
                        if domain_folder in subcat_config.domain_folders:
                            subcategories.append(subcat_name)

            # Create note record
            note = NoteRecord(
                path=file_path,
                title=title,
                domain_folder=domain_folder or "root",
                note_type=note_type,
                primary_root_category=primary_root_category,
                secondary_root_categories=secondary_root_categories,
                subcategories=subcategories,
                wikilinks_out=wikilinks_out,
                has_slope_section=has_slope,
                generated_status=generated_status,
                created_at=created_at,
                modified_at=stat.st_mtime,
                file_size=stat.st_size,
                line_count=len(content.split("\n")),
            )

            return note

        except Exception as e:
            logger.error(f"Failed to scan note {file_path}: {e}")
            return None

    def scan_vault(self, limit: Optional[int] = None) -> List[NoteRecord]:
        """Scan all notes in the vault."""
        notes = []

        if not self.vault_path.exists():
            logger.error(f"Vault path does not exist: {self.vault_path}")
            return notes

        # Find all markdown files
        markdown_files = list(self.vault_path.rglob("*.md"))
        logger.info(f"Found {len(markdown_files)} markdown files in vault")

        for i, file_path in enumerate(markdown_files):
            if limit and i >= limit:
                break

            note = self.scan_note(file_path)
            if note:
                notes.append(note)

            if (i + 1) % 100 == 0:
                logger.info(f"Scanned {i + 1} files...")

        logger.info(f"Successfully scanned {len(notes)} notes")
        return notes

    def scan_domain_folder(
        self, domain_folder: str, limit: Optional[int] = None
    ) -> List[NoteRecord]:
        """Scan notes in a specific domain folder."""
        notes = []

        domain_path = self.vault_path / domain_folder
        if not domain_path.exists():
            logger.warning(f"Domain folder does not exist: {domain_folder}")
            return notes

        # Find markdown files in domain folder
        markdown_files = list(domain_path.rglob("*.md"))
        logger.info(f"Found {len(markdown_files)} markdown files in {domain_folder}")

        for i, file_path in enumerate(markdown_files):
            if limit and i >= limit:
                break

            note = self.scan_note(file_path)
            if note:
                notes.append(note)

        logger.info(f"Successfully scanned {len(notes)} notes in {domain_folder}")
        return notes

    def get_vault_statistics(self, notes: List[NoteRecord]) -> Dict[str, Any]:
        """Get statistics about the vault."""
        from collections import Counter

        stats = {
            "total_notes": len(notes),
            "by_domain_folder": Counter(),
            "by_note_type": Counter(),
            "by_generated_status": Counter(),
            "by_root_category": Counter(),
            "notes_with_slope_sections": 0,
            "total_wikilinks": 0,
            "avg_wikilinks_per_note": 0,
            "total_file_size_mb": 0,
            "avg_file_size_kb": 0,
        }

        if not notes:
            return stats

        # Calculate statistics
        total_wikilinks = 0

        for note in notes:
            stats["by_domain_folder"][note.domain_folder] += 1
            stats["by_note_type"][note.note_type.value] += 1
            stats["by_generated_status"][note.generated_status.value] += 1

            if note.primary_root_category:
                stats["by_root_category"][note.primary_root_category.value] += 1

            if note.has_slope_section:
                stats["notes_with_slope_sections"] += 1

            total_wikilinks += len(note.wikilinks_out)
            stats["total_file_size_mb"] += note.file_size

        stats["total_wikilinks"] = total_wikilinks
        stats["avg_wikilinks_per_note"] = total_wikilinks / len(notes)
        stats["total_file_size_mb"] = stats["total_file_size_mb"] / (1024 * 1024)
        stats["avg_file_size_kb"] = (stats["total_file_size_mb"] * 1024) / len(notes)

        return stats

    def find_notes_by_pattern(
        self, pattern: str, search_content: bool = False, case_sensitive: bool = False
    ) -> List[NoteRecord]:
        """Find notes matching a pattern in title or content."""
        import fnmatch

        notes = self.scan_vault()
        matching_notes = []

        for note in notes:
            # Check title
            title_match = False
            if case_sensitive:
                title_match = fnmatch.fnmatch(note.title, pattern)
            else:
                title_match = fnmatch.fnmatch(note.title.lower(), pattern.lower())

            if title_match:
                matching_notes.append(note)
                continue

            # Check content if requested
            if search_content:
                try:
                    with open(note.path, "r", encoding="utf-8") as f:
                        content = f.read()

                    if case_sensitive:
                        content_match = pattern in content
                    else:
                        content_match = pattern.lower() in content.lower()

                    if content_match:
                        matching_notes.append(note)
                except Exception as e:
                    logger.warning(f"Failed to read content of {note.path}: {e}")

        return matching_notes

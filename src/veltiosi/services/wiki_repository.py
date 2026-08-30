"""Wiki repository service for consistent vault access."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..connectors.obsidian import ObsidianConnector
from ..indexing.backlinks import BacklinkAnalyzer
from ..indexing.classifier import NoteClassifier
from ..indexing.scanner import VaultScanner
from ..models import NoteRecord, NoteType, RootCategory
from ..settings import settings

logger = logging.getLogger(__name__)


class WikiRepository:
    """Repository for consistent vault access and note management."""

    def __init__(self, vault_path: Optional[Path] = None):
        """Initialize wiki repository."""
        self.vault_path = vault_path or settings.obsidian_vault
        self.connector = ObsidianConnector(self.vault_path)
        self.scanner = VaultScanner(self.vault_path)
        self.classifier = NoteClassifier()
        self.backlink_analyzer = BacklinkAnalyzer()

        # Cache for note records
        self._notes_cache: Optional[List[NoteRecord]] = None
        self._notes_by_path: Dict[str, NoteRecord] = {}
        self._notes_by_title: Dict[str, NoteRecord] = {}

        logger.info(f"Wiki repository initialized for vault: {self.vault_path}")

    def scan_and_classify(self, force_rescan: bool = False) -> List[NoteRecord]:
        """Scan vault and classify notes with consistent path handling."""
        if self._notes_cache is not None and not force_rescan:
            return self._notes_cache

        # Scan vault
        raw_notes = self.scanner.scan_vault()

        # Classify notes
        classified_notes = self.classifier.batch_classify(raw_notes)

        # Normalize paths to be relative to vault root
        normalized_notes = []
        for note in classified_notes:
            # Ensure path is relative to vault
            if note.path.is_absolute():
                try:
                    note.path = note.path.relative_to(self.vault_path)
                except ValueError:
                    logger.warning(f"Note path {note.path} not relative to vault {self.vault_path}")
                    continue

            # Update caches
            path_str = str(note.path)
            self._notes_by_path[path_str] = note
            self._notes_by_title[note.title] = note

            normalized_notes.append(note)

        # Build backlink graph
        self.backlink_analyzer.build_graph(normalized_notes)

        # Update backlinks in notes
        notes_with_backlinks = self.backlink_analyzer.calculate_backlinks(normalized_notes)
        # Create a mapping from path to backlinks
        backlink_map = {}
        for note in notes_with_backlinks:
            backlink_map[str(note.path)] = note.wikilinks_in

        for note in normalized_notes:
            note.wikilinks_in = backlink_map.get(str(note.path), [])

        self._notes_cache = normalized_notes
        logger.info(f"Scanned and classified {len(normalized_notes)} notes")
        return normalized_notes

    def get_note_by_path(self, path: str) -> Optional[NoteRecord]:
        """Get note by its relative path."""
        self._ensure_cache()
        return self._notes_by_path.get(path)

    def get_note_by_title(self, title: str) -> Optional[NoteRecord]:
        """Get note by title."""
        self._ensure_cache()
        return self._notes_by_title.get(title)

    def get_notes_by_category(self, category: RootCategory) -> List[NoteRecord]:
        """Get notes by root category."""
        notes = self.scan_and_classify()
        return [n for n in notes if n.primary_root_category == category]

    def get_notes_by_subcategory(self, subcategory: str) -> List[NoteRecord]:
        """Get notes by subcategory."""
        notes = self.scan_and_classify()
        return [n for n in notes if subcategory in n.subcategories]

    def get_notes_by_type(self, note_type: NoteType) -> List[NoteRecord]:
        """Get notes by note type."""
        notes = self.scan_and_classify()
        return [n for n in notes if n.note_type == note_type]

    def get_notes_by_domain(self, domain_folder: str) -> List[NoteRecord]:
        """Get notes by domain folder."""
        notes = self.scan_and_classify()
        return [n for n in notes if n.domain_folder == domain_folder]

    def get_related_notes(self, note: NoteRecord, max_notes: int = 10) -> List[NoteRecord]:
        """Get notes related to the given note via wikilinks."""
        notes = self.scan_and_classify()

        # Collect notes linked from this note
        related_paths = set()

        # Outgoing links
        for link in note.wikilinks_out:
            linked_note = self.get_note_by_title(link)
            if linked_note:
                related_paths.add(str(linked_note.path))

        # Incoming links
        for backlink_path in note.wikilinks_in:
            related_paths.add(backlink_path)

        # Get the actual note objects
        related_notes = []
        for path in list(related_paths)[:max_notes]:
            note_obj = self.get_note_by_path(path)
            if note_obj:
                related_notes.append(note_obj)

        return related_notes

    def read_note_content(self, note_path) -> Optional[str]:
        """Read content of a note by its path (absolute or relative)."""
        path = Path(note_path) if not isinstance(note_path, Path) else note_path
        # If absolute, try to read directly; else delegate to connector (relative)
        if path.is_absolute():
            try:
                return path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return None
        return self.connector.read_note(str(path))

    def write_note(self, note_path, content: str, backup: bool = False) -> bool:
        """Write content to a note (accepts absolute Path or vault-relative str/Path)."""
        path = Path(note_path) if not isinstance(note_path, Path) else note_path
        if path.is_absolute():
            # Write directly
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self._notes_cache = None
            self._notes_by_path.clear()
            self._notes_by_title.clear()
            return True
        success = self.connector.write_note(str(path), content, backup)
        if success:
            self._notes_cache = None
            self._notes_by_path.clear()
            self._notes_by_title.clear()
        return success

    def append_to_note(self, note_path, content: str) -> bool:
        """Append content to a note."""
        path = Path(note_path) if not isinstance(note_path, Path) else note_path
        success = self.connector.append_to_note(str(path), content)
        if success:
            # Invalidate cache since we modified the vault
            self._notes_cache = None
        return success

    def update_generated_section(
        self,
        note_path: str,
        section_name: str,
        content: str,
        start_marker: Optional[str] = None,
        end_marker: Optional[str] = None,
    ) -> bool:
        """Update a generated section in a note."""
        if start_marker is None:
            start_marker = settings.generation_rules.generated_sections["start_marker"]
        if end_marker is None:
            end_marker = settings.generation_rules.generated_sections["end_marker"]

        # Read existing content
        existing_content = self.read_note_content(note_path)
        if existing_content is None:
            logger.warning(f"Note not found for section update: {note_path}")
            return False

        # Update section
        from ..utils.markdown import replace_generated_section

        updated_content = replace_generated_section(
            existing_content, section_name, content, start_marker, end_marker
        )

        # Write back
        return self.write_note(note_path, updated_content)

    def get_vault_statistics(self) -> Dict[str, any]:
        """Get statistics about the vault."""
        notes = self.scan_and_classify()

        stats = {
            "total_notes": len(notes),
            "notes_by_type": {},
            "notes_by_category": {},
            "notes_by_domain": {},
            "backlink_stats": self.backlink_analyzer.get_backlink_statistics(),
        }

        # Count by note type
        for note in notes:
            note_type = note.note_type.value
            stats["notes_by_type"][note_type] = stats["notes_by_type"].get(note_type, 0) + 1

            # Count by category
            if note.primary_root_category:
                category = note.primary_root_category.value
                stats["notes_by_category"][category] = (
                    stats["notes_by_category"].get(category, 0) + 1
                )

            # Count by domain
            domain = note.domain_folder
            stats["notes_by_domain"][domain] = stats["notes_by_domain"].get(domain, 0) + 1

        return stats

    def scan_all_notes(self, force_rescan: bool = False) -> List[NoteRecord]:
        """Alias for scan_and_classify for compatibility."""
        return self.scan_and_classify(force_rescan=force_rescan)

    def search_notes_by_content(self, query: str) -> List[NoteRecord]:
        """Return notes whose title or content contains the query string (case-insensitive)."""
        notes = self.scan_and_classify()
        query_lower = query.lower()
        results = []
        for note in notes:
            if query_lower in note.title.lower():
                results.append(note)
                continue
            content = self.read_note_content(note.path)
            if content and query_lower in content.lower():
                results.append(note)
        return results

    def find_notes_by_pattern(self, pattern: str) -> List[NoteRecord]:
        """Find notes matching a pattern in title or content."""
        return self.connector.find_notes_by_pattern(pattern)

    def _ensure_cache(self) -> None:
        """Ensure notes cache is populated."""
        if self._notes_cache is None:
            self.scan_and_classify()

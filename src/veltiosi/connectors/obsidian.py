"""Obsidian vault connector for Veltiosi."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from veltiosi.models import NoteRecord, NoteType, GeneratedStatus
from veltiosi.settings import settings
from veltiosi.utils import dates, markdown, text


class ObsidianConnector:
    """Connector for interacting with the Obsidian vault."""

    def __init__(self, vault_path: Optional[Path] = None):
        """Initialize the connector.

        Args:
            vault_path: Path to Obsidian vault (default: from settings)
        """
        self.vault_path = vault_path or settings.obsidian_vault
        if not self.vault_path.exists():
            raise ValueError(f"Obsidian vault not found at {self.vault_path}")

    def scan_vault(self) -> List[NoteRecord]:
        """Scan the vault and return all notes.

        Returns:
            List of NoteRecord objects
        """
        notes = []
        ignored_paths = set(settings.generation_rules.ignored_paths)

        for md_file in self.vault_path.rglob("*.md"):
            # Check if file should be ignored
            if any(ignored in str(md_file) for ignored in ignored_paths):
                continue

            try:
                note = self._read_note(md_file)
                if note:
                    notes.append(note)
            except Exception as e:
                print(f"Error reading {md_file}: {e}")

        return notes

    def _read_note(self, file_path: Path) -> Optional[NoteRecord]:
        """Read a note file and create a NoteRecord.

        Args:
            file_path: Path to note file

        Returns:
            NoteRecord or None if not a valid note
        """
        if not file_path.exists():
            return None

        # Get relative path from vault root
        rel_path = file_path.relative_to(self.vault_path)

        # Read file content
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        # Extract basic information
        title = markdown.extract_heading(content) or file_path.stem
        domain_folder = self._extract_domain_folder(rel_path)

        # Analyze content
        wikilinks_out = markdown.extract_wikilinks(content)
        has_slope_section = markdown.has_slope_section(content)

        # Get file metadata
        stat = file_path.stat()
        created_at = datetime.fromtimestamp(stat.st_ctime)
        modified_at = datetime.fromtimestamp(stat.st_mtime)
        file_size = stat.st_size
        line_count = len(content.splitlines())

        # Determine note type
        note_type = self._classify_note_type(content, rel_path)

        # Determine generated status
        generated_status = self._determine_generated_status(content)

        # Create note record
        note = NoteRecord(
            path=rel_path,
            title=title,
            domain_folder=domain_folder,
            note_type=note_type,
            wikilinks_out=wikilinks_out,
            wikilinks_in=[],  # Will be populated later
            has_slope_section=has_slope_section,
            generated_status=generated_status,
            created_at=created_at,
            modified_at=modified_at,
            file_size=file_size,
            line_count=line_count,
        )

        return note

    def _extract_domain_folder(self, rel_path: Path) -> str:
        """Extract domain folder from relative path.

        Args:
            rel_path: Relative path from vault root

        Returns:
            Domain folder name
        """
        # Get the first component of the path
        parts = rel_path.parts
        if len(parts) > 1:
            return parts[0]
        else:
            return "root"

    def _classify_note_type(self, content: str, rel_path: Path) -> NoteType:
        """Classify note type based on content and path.

        Args:
            content: Note content
            rel_path: Relative path

        Returns:
            NoteType
        """
        path_str = str(rel_path).lower()

        # Check for specific patterns
        if "moc" in path_str or "maps-of-content" in path_str:
            return NoteType.MOC
        elif "weekly" in path_str and "synthesis" in path_str:
            return NoteType.SYNTHESIS
        elif "practice" in path_str or "compounding" in content.lower():
            return NoteType.COMPOUNDING_PAGE
        elif "summary" in path_str or "summary" in content.lower():
            return NoteType.SOURCE_SUMMARY
        elif "task" in path_str or "task" in content.lower():
            return NoteType.TASK_LINKED
        elif "index" in path_str or "index" in content.lower():
            return NoteType.GENERATED_INDEX
        elif "reference" in path_str or "reference" in content.lower():
            return NoteType.REFERENCE
        else:
            # Default to concept for most notes
            return NoteType.CONCEPT

    def _determine_generated_status(self, content: str) -> GeneratedStatus:
        """Determine if note is generated, manual, or mixed.

        Args:
            content: Note content

        Returns:
            GeneratedStatus
        """
        start_marker = settings.generation_rules.generated_sections["start_marker"]
        end_marker = settings.generation_rules.generated_sections["end_marker"]

        has_generated = start_marker in content and end_marker in content

        # Check if entire note looks generated
        lines = content.split("\n")
        if len(lines) <= 5 and all(
            line.strip().startswith("#") or not line.strip() for line in lines
        ):
            return GeneratedStatus.GENERATED

        if has_generated:
            # Check if there's substantial manual content outside generated sections
            # Simple heuristic: if more than 50% of lines are outside generated sections
            total_lines = len(lines)
            generated_lines = 0

            in_generated = False
            for line in lines:
                if start_marker in line:
                    in_generated = True
                elif end_marker in line:
                    in_generated = False
                elif in_generated:
                    generated_lines += 1

            manual_lines = total_lines - generated_lines
            if manual_lines > generated_lines * 2:  # More than twice as many manual lines
                return GeneratedStatus.MIXED
            else:
                return GeneratedStatus.GENERATED

        return GeneratedStatus.MANUAL

    def count_notes(self) -> int:
        """Count total notes in vault.

        Returns:
            Number of notes
        """
        count = 0
        ignored_paths = set(settings.generation_rules.ignored_paths)

        for md_file in self.vault_path.rglob("*.md"):
            if any(ignored in str(md_file) for ignored in ignored_paths):
                continue
            count += 1

        return count

    def read_note(self, note_path: str) -> Optional[str]:
        """Read a note by its path.

        Args:
            note_path: Path relative to vault root

        Returns:
            Note content or None if not found
        """
        full_path = self.vault_path / note_path
        if not full_path.exists():
            return None

        return full_path.read_text(encoding="utf-8", errors="ignore")

    def write_note(self, note_path: str, content: str, backup: bool = False) -> bool:
        """Write a note to the vault.

        Args:
            note_path: Path relative to vault root
            content: Note content
            backup: Whether to create a backup of existing file

        Returns:
            True if successful
        """
        full_path = self.vault_path / note_path

        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Backup existing file
        if backup and full_path.exists():
            backup_path = full_path.with_suffix(
                f".md.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            full_path.rename(backup_path)

        # Write file
        full_path.write_text(content, encoding="utf-8")
        return True

    def append_to_note(self, note_path: str, content: str) -> bool:
        """Append content to a note.

        Args:
            note_path: Path relative to vault root
            content: Content to append

        Returns:
            True if successful
        """
        full_path = self.vault_path / note_path

        if not full_path.exists():
            return self.write_note(note_path, content)

        # Read existing content
        existing = full_path.read_text(encoding="utf-8", errors="ignore")

        # Append new content
        new_content = existing.rstrip() + "\n\n" + content.strip()

        # Write back
        full_path.write_text(new_content, encoding="utf-8")
        return True

    def update_generated_section(
        self,
        note_path: str,
        section_name: str,
        new_content: str,
        dry_run: bool = False,
    ) -> Tuple[bool, str]:
        """Update a generated section in a note.

        Args:
            note_path: Path relative to vault root
            section_name: Name of the section
            new_content: New section content
            dry_run: If True, return what would be changed without writing

        Returns:
            Tuple of (success, message)
        """
        full_path = self.vault_path / note_path

        if not full_path.exists():
            return False, f"Note not found: {note_path}"

        # Read existing content
        existing = full_path.read_text(encoding="utf-8", errors="ignore")

        # Get markers from settings
        start_marker = settings.generation_rules.generated_sections["start_marker"]
        end_marker = settings.generation_rules.generated_sections["end_marker"]

        # Update the section
        updated = markdown.replace_generated_section(
            existing,
            section_name,
            new_content,
            start_marker,
            end_marker,
        )

        if dry_run:
            # Compare before and after
            if existing == updated:
                return True, "No changes needed"
            else:
                return True, f"Would update section '{section_name}' in {note_path}"

        # Write back if changed
        if existing != updated:
            full_path.write_text(updated, encoding="utf-8")
            return True, f"Updated section '{section_name}' in {note_path}"
        else:
            return True, "No changes needed"

    def append_to_log(self, entry_type: str, description: str) -> bool:
        """Append an entry to the log file.

        Args:
            entry_type: Type of entry (index, ingest, task-complete, etc.)
            description: Description of the entry

        Returns:
            True if successful
        """
        if not settings.generation_rules.logging["append_to_log_md"]:
            return False

        log_path = self.vault_path / "log.md"

        # Create log file if it doesn't exist
        if not log_path.exists():
            log_content = "# Wiki Log\n\n*Chronological, append‑only record of wiki activity.*\n\n"
            log_path.write_text(log_content, encoding="utf-8")

        # Read existing log
        log_content = log_path.read_text(encoding="utf-8", errors="ignore")

        # Create log entry
        today = datetime.now().strftime("%Y-%m-%d")
        entry_format = settings.generation_rules.logging["log_entry_format"]
        entry = entry_format.format(date=today, type=entry_type, description=description)

        # Append entry
        # Find where to insert (before the --- separator if present)
        if "---\n" in log_content:
            parts = log_content.split("---\n", 1)
            new_log = parts[0] + entry + "\n\n---\n" + parts[1]
        else:
            new_log = log_content.rstrip() + "\n\n" + entry + "\n"

        # Write back
        log_path.write_text(new_log, encoding="utf-8")
        return True

    def get_note_backlinks(self, notes: List[NoteRecord]) -> Dict[str, List[str]]:
        """Calculate backlinks for all notes.

        Args:
            notes: List of NoteRecord objects

        Returns:
            Dict mapping note path to list of backlinks
        """
        # Build a mapping from normalized link to note path
        link_to_note = {}
        for note in notes:
            # Use the note path without .md as the canonical link
            canonical_path = str(note.path).replace(".md", "")
            link_to_note[canonical_path] = str(note.path)

            # Also map the title (simplified)
            title_slug = text.slugify(note.title)
            if title_slug and title_slug != canonical_path:
                link_to_note[title_slug] = str(note.path)

        # Calculate backlinks
        backlinks = {str(note.path): [] for note in notes}

        for note in notes:
            for link in note.wikilinks_out:
                # Normalize the link
                normalized_link = self._normalize_link_for_backlink(link, note.path)

                # Find which note this links to
                target_note = link_to_note.get(normalized_link)
                if target_note and target_note != str(note.path):
                    backlinks[target_note].append(str(note.path))

        return backlinks

    def _normalize_link_for_backlink(self, link: str, source_path: Path) -> str:
        """Normalize a link for backlink calculation.

        Args:
            link: Wikilink
            source_path: Path of source note

        Returns:
            Normalized link
        """
        # Remove alias
        link = link.split("|")[0].strip()

        # Remove .md extension if present
        if link.endswith(".md"):
            link = link[:-3]

        # If link contains /, it might be a path
        if "/" in link:
            # Try to resolve relative to source path's parent
            try:
                # This is simplified - actual Obsidian resolution is complex
                return link
            except:
                pass

        return link

    def find_notes_by_pattern(self, pattern: str) -> List[NoteRecord]:
        """Find notes matching a pattern in title or content.

        Args:
            pattern: Search pattern (regex)

        Returns:
            List of matching notes
        """
        notes = self.scan_vault()
        matching = []

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            # Fall back to simple substring search
            pattern_lower = pattern.lower()
            for note in notes:
                if pattern_lower in note.title.lower():
                    matching.append(note)
                else:
                    # Check content
                    content = self.read_note(str(note.path))
                    if content and pattern_lower in content.lower():
                        matching.append(note)
            return matching

        # Use regex search
        for note in notes:
            if regex.search(note.title):
                matching.append(note)
            else:
                # Check content
                content = self.read_note(str(note.path))
                if content and regex.search(content):
                    matching.append(note)

        return matching

    def get_vault_stats(self) -> Dict[str, any]:
        """Get statistics about the vault.

        Returns:
            Dict with vault statistics
        """
        notes = self.scan_vault()

        # Calculate backlinks
        backlinks = self.get_note_backlinks(notes)
        for note in notes:
            note.wikilinks_in = backlinks.get(str(note.path), [])

        # Calculate statistics
        total_notes = len(notes)
        total_links = sum(len(note.wikilinks_out) for note in notes)
        orphan_notes = [note for note in notes if not note.wikilinks_in]

        # Count by domain folder
        by_domain = {}
        for note in notes:
            domain = note.domain_folder
            by_domain[domain] = by_domain.get(domain, 0) + 1

        # Count by note type
        by_type = {}
        for note in notes:
            note_type = note.note_type.value
            by_type[note_type] = by_type.get(note_type, 0) + 1

        # Count by generated status
        by_generated = {}
        for note in notes:
            status = note.generated_status.value
            by_generated[status] = by_generated.get(status, 0) + 1

        return {
            "total_notes": total_notes,
            "total_links": total_links,
            "orphan_notes": len(orphan_notes),
            "notes_with_slope": len([n for n in notes if n.has_slope_section]),
            "by_domain": by_domain,
            "by_type": by_type,
            "by_generated": by_generated,
            "average_links_per_note": total_links / total_notes if total_notes > 0 else 0,
        }

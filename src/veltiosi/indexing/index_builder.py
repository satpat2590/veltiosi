"""Index builder for generating MOCs and category indexes."""

import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import NoteRecord, NoteType
from ..settings import settings
from ..utils.markdown import generate_markdown_table

logger = logging.getLogger(__name__)


class IndexBuilder:
    """Builder for generating indexes and MOCs."""

    def __init__(self, vault_path: Optional[Path] = None):
        """Initialize index builder."""
        self.vault_path = vault_path or settings.obsidian_vault

        # Setup Jinja2 templates
        template_dir = Path(__file__).parent.parent / "templates"
        if template_dir.exists():
            self.env = Environment(
                loader=FileSystemLoader(template_dir),
                autoescape=select_autoescape(["html", "xml"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        else:
            self.env = None
            logger.warning(f"Template directory not found: {template_dir}")

        logger.info("Index builder initialized")

    def build_root_category_index(
        self, notes: List[NoteRecord], root_category: str, include_generated_marker: bool = True
    ) -> str:
        """Build index for a root category."""
        # Filter notes by root category
        category_notes = [
            note
            for note in notes
            if note.primary_root_category and note.primary_root_category.value == root_category
        ]

        if not category_notes:
            logger.warning(f"No notes found for root category: {root_category}")
            return ""

        # Get category config
        category_config = settings.root_categories.get(root_category)
        if not category_config:
            logger.error(f"No config found for root category: {root_category}")
            return ""

        # Group notes by subcategory
        notes_by_subcat: Dict[str, List[NoteRecord]] = defaultdict(list)
        uncategorized_notes = []

        for note in category_notes:
            if note.subcategories:
                for subcat in note.subcategories:
                    notes_by_subcat[subcat].append(note)
            else:
                uncategorized_notes.append(note)

        # Build markdown content
        lines = []

        # Header
        lines.append(f"# {category_config.display_name}")
        if category_config.description:
            lines.append(f"\n{category_config.description}\n")

        # Generated marker
        if include_generated_marker:
            lines.append("<!-- veltiosi:generated:start -->")
            lines.append("")

        # Subcategory sections
        for subcat_name in sorted(notes_by_subcat.keys()):
            subcat_config = settings.subcategories.get(subcat_name)
            if not subcat_config:
                continue

            lines.append(f"## {subcat_config.display_name}")

            if subcat_config.description:
                lines.append(f"\n{subcat_config.description}\n")

            # List notes
            subcat_notes = notes_by_subcat[subcat_name]
            for note in sorted(subcat_notes, key=lambda n: n.title):
                note_type_emoji = self._get_note_type_emoji(note.note_type)
                lines.append(f"- {note_type_emoji} [[{note.title}]]")

                # Add note metadata if available
                metadata_parts = []
                if note.has_slope_section:
                    metadata_parts.append("📈")
                if note.generated_status.value != "manual":
                    metadata_parts.append("🤖")

                if metadata_parts:
                    lines[-1] += f" {' '.join(metadata_parts)}"

            lines.append("")

        # Uncategorized notes section
        if uncategorized_notes:
            lines.append("## Uncategorized")
            lines.append("")

            for note in sorted(uncategorized_notes, key=lambda n: n.title):
                note_type_emoji = self._get_note_type_emoji(note.note_type)
                lines.append(f"- {note_type_emoji} [[{note.title}]]")

            lines.append("")

        # Statistics
        lines.append("## Statistics")
        lines.append("")
        lines.append(f"- **Total notes**: {len(category_notes)}")
        lines.append(f"- **Subcategories**: {len(notes_by_subcat)}")
        lines.append(f"- **Uncategorized**: {len(uncategorized_notes)}")

        # Generated marker end
        if include_generated_marker:
            lines.append("")
            lines.append("<!-- veltiosi:generated:end -->")

        return "\n".join(lines)

    def build_subcategory_index(
        self, notes: List[NoteRecord], subcategory: str, include_generated_marker: bool = True
    ) -> str:
        """Build index for a subcategory."""
        # Get subcategory config
        subcat_config = settings.subcategories.get(subcategory)
        if not subcat_config:
            logger.error(f"No config found for subcategory: {subcategory}")
            return ""

        # Filter notes by subcategory
        subcat_notes = [note for note in notes if subcategory in note.subcategories]

        if not subcat_notes:
            logger.warning(f"No notes found for subcategory: {subcategory}")
            return ""

        # Build markdown content
        lines = []

        # Header
        lines.append(f"# {subcat_config.display_name}")

        # Description
        if subcat_config.description:
            lines.append(f"\n{subcat_config.description}\n")

        # Generated marker
        if include_generated_marker:
            lines.append("<!-- veltiosi:generated:start -->")
            lines.append("")

        # Notes table
        table_data = []
        for note in sorted(subcat_notes, key=lambda n: n.title):
            row = [
                f"[[{note.title}]]",
                note.domain_folder or "root",
                self._get_note_type_display(note.note_type),
                "📈" if note.has_slope_section else "",
                "🤖" if note.generated_status.value != "manual" else "",
            ]
            table_data.append(row)

        headers = ["Note", "Domain", "Type", "Slope", "Generated"]
        table = generate_markdown_table(headers, table_data)
        lines.append(table)
        lines.append("")

        # Related subcategories
        related_subcats = self._find_related_subcategories(subcat_notes, subcategory)
        if related_subcats:
            lines.append("## Related Subcategories")
            lines.append("")
            for related_subcat in related_subcats:
                related_config = settings.subcategories.get(related_subcat)
                if related_config:
                    lines.append(f"- [[{related_config.moc_path}]]")
            lines.append("")

        # Statistics
        lines.append("## Statistics")
        lines.append("")
        lines.append(f"- **Total notes**: {len(subcat_notes)}")

        # Domain distribution
        domain_counts = defaultdict(int)
        for note in subcat_notes:
            domain_counts[note.domain_folder] += 1

        if domain_counts:
            lines.append("- **By domain**:")
            for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  - {domain}: {count}")

        # Generated marker end
        if include_generated_marker:
            lines.append("")
            lines.append("<!-- veltiosi:generated:end -->")

        return "\n".join(lines)

    def build_domain_index(
        self, notes: List[NoteRecord], domain_folder: str, include_generated_marker: bool = True
    ) -> str:
        """Build index for a domain folder."""
        # Filter notes by domain folder
        domain_notes = [note for note in notes if note.domain_folder == domain_folder]

        if not domain_notes:
            logger.warning(f"No notes found for domain folder: {domain_folder}")
            return ""

        # Get domain config
        domain_config = settings.domain_folders.get(domain_folder)

        # Build markdown content
        lines = []

        # Header
        lines.append(f"# {domain_folder}")

        # Description
        if domain_config and domain_config.description:
            lines.append(f"\n{domain_config.description}\n")

        # Generated marker
        if include_generated_marker:
            lines.append("<!-- veltiosi:generated:start -->")
            lines.append("")

        # Group by subcategory
        notes_by_subcat: Dict[str, List[NoteRecord]] = defaultdict(list)
        uncategorized_notes = []

        for note in domain_notes:
            if note.subcategories:
                for subcat in note.subcategories:
                    notes_by_subcat[subcat].append(note)
            else:
                uncategorized_notes.append(note)

        # Subcategory sections
        for subcat_name in sorted(notes_by_subcat.keys()):
            subcat_config = settings.subcategories.get(subcat_name)
            if not subcat_config:
                continue

            lines.append(f"## {subcat_config.display_name}")
            lines.append("")

            # List notes
            subcat_notes = notes_by_subcat[subcat_name]
            for note in sorted(subcat_notes, key=lambda n: n.title):
                note_type_emoji = self._get_note_type_emoji(note.note_type)
                lines.append(f"- {note_type_emoji} [[{note.title}]]")

            lines.append("")

        # Uncategorized notes
        if uncategorized_notes:
            lines.append("## Uncategorized")
            lines.append("")

            for note in sorted(uncategorized_notes, key=lambda n: n.title):
                note_type_emoji = self._get_note_type_emoji(note.note_type)
                lines.append(f"- {note_type_emoji} [[{note.title}]]")

            lines.append("")

        # Statistics
        lines.append("## Statistics")
        lines.append("")
        lines.append(f"- **Total notes**: {len(domain_notes)}")
        lines.append(f"- **Subcategories**: {len(notes_by_subcat)}")
        lines.append(f"- **Uncategorized**: {len(uncategorized_notes)}")

        # Root category distribution
        root_counts = defaultdict(int)
        for note in domain_notes:
            if note.primary_root_category:
                root_counts[note.primary_root_category.value] += 1

        if root_counts:
            lines.append("- **By root category**:")
            for root, count in sorted(root_counts.items(), key=lambda x: x[1], reverse=True):
                root_config = settings.root_categories.get(root)
                display_name = root_config.display_name if root_config else root
                lines.append(f"  - {display_name}: {count}")

        # Generated marker end
        if include_generated_marker:
            lines.append("")
            lines.append("<!-- veltiosi:generated:end -->")

        return "\n".join(lines)

    def build_master_index(
        self, notes: List[NoteRecord], include_generated_marker: bool = True
    ) -> str:
        """Build master index of the entire vault."""
        # Build markdown content
        lines = []

        # Header
        lines.append("# Vault Master Index")
        lines.append("\n*Generated by Veltiosi*\n")

        # Generated marker
        if include_generated_marker:
            lines.append("<!-- veltiosi:generated:start -->")
            lines.append("")

        # Root category summary
        lines.append("## Root Categories")
        lines.append("")

        for root_name, root_config in settings.root_categories.items():
            # Count notes in this root category
            root_notes = [
                note
                for note in notes
                if note.primary_root_category and note.primary_root_category.value == root_name
            ]

            lines.append(f"### {root_config.display_name}")
            lines.append(f"- **Notes**: {len(root_notes)}")
            lines.append(f"- **MOC**: [[{root_config.moc_path}]]")

            if root_config.description:
                lines.append(f"- **Description**: {root_config.description}")

            lines.append("")

        # Domain folders summary
        lines.append("## Domain Folders")
        lines.append("")

        # Group notes by domain
        notes_by_domain = defaultdict(list)
        for note in notes:
            notes_by_domain[note.domain_folder].append(note)

        for domain in sorted(notes_by_domain.keys()):
            domain_notes = notes_by_domain[domain]
            lines.append(f"- **{domain}**: {len(domain_notes)} notes")

        lines.append("")

        # Statistics
        lines.append("## Statistics")
        lines.append("")
        lines.append(f"- **Total notes**: {len(notes)}")

        # Note type distribution
        type_counts = defaultdict(int)
        for note in notes:
            type_counts[note.note_type.value] += 1

        if type_counts:
            lines.append("- **By note type**:")
            for note_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  - {note_type}: {count}")

        # Generated status distribution
        status_counts = defaultdict(int)
        for note in notes:
            status_counts[note.generated_status.value] += 1

        if status_counts:
            lines.append("- **By generation status**:")
            for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  - {status}: {count}")

        # Generated marker end
        if include_generated_marker:
            lines.append("")
            lines.append("<!-- veltiosi:generated:end -->")

        return "\n".join(lines)

    def write_index(self, content: str, output_path: Path, dry_run: bool = False) -> bool:
        """Write index content to file."""
        if dry_run:
            logger.info(f"Would write index to: {output_path}")
            logger.info(f"Content length: {len(content)} characters")
            return True

        try:
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"Index written to: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to write index to {output_path}: {e}")
            return False

    def build_all_indexes(
        self, notes: List[NoteRecord], dry_run: bool = False
    ) -> Dict[str, List[str]]:
        """Build all indexes for the vault."""
        results = {
            "written": [],
            "skipped": [],
            "failed": [],
        }

        # Build root category indexes
        for root_name, root_config in settings.root_categories.items():
            content = self.build_root_category_index(notes, root_name)
            if not content:
                results["skipped"].append(f"root_{root_name}")
                continue

            output_path = self.vault_path / root_config.moc_path
            success = self.write_index(content, output_path, dry_run)

            if success:
                results["written"].append(f"root_{root_name}")
            else:
                results["failed"].append(f"root_{root_name}")

        # Build subcategory indexes
        for subcat_name, subcat_config in settings.subcategories.items():
            content = self.build_subcategory_index(notes, subcat_name)
            if not content:
                results["skipped"].append(f"subcat_{subcat_name}")
                continue

            output_path = self.vault_path / subcat_config.moc_path
            success = self.write_index(content, output_path, dry_run)

            if success:
                results["written"].append(f"subcat_{subcat_name}")
            else:
                results["failed"].append(f"subcat_{subcat_name}")

        # Build domain indexes
        domain_folders = set(note.domain_folder for note in notes if note.domain_folder != "root")
        for domain in domain_folders:
            content = self.build_domain_index(notes, domain)
            if not content:
                results["skipped"].append(f"domain_{domain}")
                continue

            # Determine output path for domain index
            output_path = self.vault_path / domain / "index.md"
            success = self.write_index(content, output_path, dry_run)

            if success:
                results["written"].append(f"domain_{domain}")
            else:
                results["failed"].append(f"domain_{domain}")

        # Build master index
        master_content = self.build_master_index(notes)
        if master_content:
            output_path = self.vault_path / "index.md"
            success = self.write_index(master_content, output_path, dry_run)

            if success:
                results["written"].append("master_index")
            else:
                results["failed"].append("master_index")

        logger.info(
            f"Index building complete: {len(results['written'])} written, "
            f"{len(results['skipped'])} skipped, {len(results['failed'])} failed"
        )

        return results

    def _get_note_type_emoji(self, note_type: NoteType) -> str:
        """Get emoji for note type."""
        emoji_map = {
            NoteType.CONCEPT: "📝",
            NoteType.SOURCE_SUMMARY: "📚",
            NoteType.COMPOUNDING_PAGE: "📈",
            NoteType.SYNTHESIS: "🧩",
            NoteType.MOC: "🗺️",
            NoteType.TASK_LINKED: "✅",
            NoteType.REFERENCE: "🔗",
            NoteType.GENERATED_INDEX: "🤖",
        }
        return emoji_map.get(note_type, "📝")

    def _get_note_type_display(self, note_type: NoteType) -> str:
        """Get display name for note type."""
        display_map = {
            NoteType.CONCEPT: "Concept",
            NoteType.SOURCE_SUMMARY: "Source Summary",
            NoteType.COMPOUNDING_PAGE: "Compounding Page",
            NoteType.SYNTHESIS: "Synthesis",
            NoteType.MOC: "MOC",
            NoteType.TASK_LINKED: "Task Linked",
            NoteType.REFERENCE: "Reference",
            NoteType.GENERATED_INDEX: "Generated Index",
        }
        return display_map.get(note_type, "Concept")

    def _find_related_subcategories(self, notes: List[NoteRecord], current_subcat: str) -> Set[str]:
        """Find subcategories that are related to the current one."""
        related = set()

        for note in notes:
            for subcat in note.subcategories:
                if subcat != current_subcat:
                    related.add(subcat)

        return related

    def check_index_consistency(self, notes: List[NoteRecord]) -> Dict[str, any]:
        """Check consistency of existing indexes."""
        issues = []

        # Check root category MOCs
        for root_name, root_config in settings.root_categories.items():
            moc_path = self.vault_path / root_config.moc_path
            if not moc_path.exists():
                issues.append(
                    {
                        "type": "missing_moc",
                        "path": str(moc_path),
                        "category": f"root_{root_name}",
                        "message": f"Root category MOC not found: {moc_path}",
                    }
                )

        # Check subcategory MOCs
        for subcat_name, subcat_config in settings.subcategories.items():
            moc_path = self.vault_path / subcat_config.moc_path
            if not moc_path.exists():
                issues.append(
                    {
                        "type": "missing_moc",
                        "path": str(moc_path),
                        "category": f"subcat_{subcat_name}",
                        "message": f"Subcategory MOC not found: {moc_path}",
                    }
                )

        # Check for orphan notes (not in any MOC)
        # This is a simplified check - full check would parse all MOCs
        notes_in_mocs = set()

        # Count notes with categories
        categorized_notes = [
            note for note in notes if note.primary_root_category or note.subcategories
        ]

        uncategorized_notes = [
            note for note in notes if not note.primary_root_category and not note.subcategories
        ]

        return {
            "total_notes": len(notes),
            "categorized_notes": len(categorized_notes),
            "uncategorized_notes": len(uncategorized_notes),
            "missing_mocs": len([i for i in issues if i["type"] == "missing_moc"]),
            "issues": issues,
            "uncategorized_note_paths": [str(note.path) for note in uncategorized_notes],
        }

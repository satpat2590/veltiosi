"""Wiki ingest workflow for processing sources."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..audit import AuditLogger
from ..models import NoteRecord, NoteType, RootCategory, SourceRecord
from ..services.llm_service import llm_service
from ..services.retrieval import RetrievalService
from ..services.source_loader import SourceLoader
from ..services.wiki_repository import WikiRepository
from ..settings import settings

logger = logging.getLogger(__name__)


class WikiIngestWorkflow:
    """Workflow for ingesting sources into the wiki."""

    def __init__(self, vault_path: Optional[Path] = None):
        """Initialize wiki ingest workflow."""
        self.wiki_repo = WikiRepository(vault_path)
        self.retrieval = RetrievalService(self.wiki_repo)
        self.source_loader = SourceLoader()

    def ingest_source(
        self,
        source_path: str,
        source_type: str = "article",
        title: Optional[str] = None,
        dry_run: bool = False,
    ) -> Optional[Tuple[SourceRecord, str]]:
        """Ingest a source file or URL into the wiki."""
        logger.info(f"Ingesting source: {source_path} (type: {source_type})")

        # Load source content
        source_content, extracted_title = self.source_loader.load_source(source_path)
        if not source_content:
            logger.error(f"Failed to load source: {source_path}")
            return None

        source_title = title or extracted_title or Path(source_path).stem

        # Retrieve relevant existing notes
        relevant_notes = self.retrieval.retrieve_for_source(
            source_title=source_title,
            source_content=source_content[:5000],  # Limit content length
            source_type=source_type,
            max_notes=10,
        )

        # Build wiki context
        wiki_context = self._build_wiki_context(relevant_notes)

        # Generate ingest summary using LLM
        summary = llm_service.generate_ingest_summary(
            source_title=source_title,
            source_type=source_type,
            source_content=source_content[:5000],  # Limit content length
            wiki_context=wiki_context,
        )

        if not summary:
            logger.error("Failed to generate ingest summary")
            return None

        # Create source record
        source_record = SourceRecord(
            source_id=f"src_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            title=source_title,
            source_type=source_type,
            source_location=source_path,
            metadata={
                "ingested_at": datetime.now().isoformat(),
                "content_length": len(source_content),
                "relevant_notes_count": len(relevant_notes),
            },
        )

        # Create note content
        note_content = self._create_note_content(source_record, summary, relevant_notes)

        # Determine note path
        note_path = self._determine_note_path(source_record, relevant_notes)

        if not dry_run:
            # Save the note
            success = self.wiki_repo.write_note(note_path, note_content)
            if success:
                source_record.summary_note_path = note_path
                logger.info(f"Created summary note at: {note_path}")
            else:
                logger.error(f"Failed to write note to: {note_path}")
                return None
        else:
            logger.info(f"Dry run - would create note at: {note_path}")

        return source_record, note_content

    def _build_wiki_context(self, notes: List[NoteRecord]) -> str:
        """Build context string from relevant notes."""
        if not notes:
            return "No existing relevant notes found."

        context_parts = ["Existing relevant wiki notes:"]

        for note in notes[:5]:  # Limit to top 5 notes
            try:
                content = self.wiki_repo.read_note_content(note.path)
                if content:
                    truncated = content[:1000] + "..." if len(content) > 1000 else content
                    context_parts.append(f"\n--- [[{note.title}]] ({note.note_type.value}) ---")
                    context_parts.append(truncated)
            except Exception as e:
                logger.warning(f"Failed to read note {note.path}: {e}")

        return "\n".join(context_parts)

    def _create_note_content(
        self,
        source_record: SourceRecord,
        summary: str,
        relevant_notes: List[NoteRecord],
    ) -> str:
        """Create note content from source and summary."""
        # Extract categories from summary if possible
        categories = self._extract_categories_from_summary(summary)

        # Build note content
        lines = [
            f"# {source_record.title}",
            "",
            f"**Source Type:** {source_record.source_type}",
            f"**Source:** {source_record.source_location}",
            f"**Ingested:** {source_record.ingested_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            "",
            summary,
            "",
        ]

        # Add categories section
        if categories:
            lines.extend(
                [
                    "## Categories",
                    "",
                ]
            )

            if categories.get("root_categories"):
                lines.append("### Root Categories")
                for cat in categories["root_categories"]:
                    lines.append(f"- {cat}")
                lines.append("")

            if categories.get("subcategories"):
                lines.append("### Subcategories")
                for subcat in categories["subcategories"]:
                    lines.append(f"- {subcat}")
                lines.append("")

        # Add related notes section
        if relevant_notes:
            lines.extend(
                [
                    "## Related Notes",
                    "",
                ]
            )
            for note in relevant_notes[:5]:  # Limit to top 5
                lines.append(f"- [[{note.title}]]")
            lines.append("")

        # Add metadata
        lines.extend(
            [
                "## Metadata",
                "",
                "```json",
                json.dumps(source_record.metadata, indent=2, default=str),
                "```",
                "",
                "---",
                f"*Generated by Veltiosi ingest workflow on {datetime.now().strftime('%Y-%m-%d')}*",
            ]
        )

        return "\n".join(lines)

    def _extract_categories_from_summary(self, summary: str) -> Dict[str, List[str]]:
        """Extract categories from LLM summary."""
        categories = {
            "root_categories": [],
            "subcategories": [],
        }

        # Simple extraction - look for category mentions
        summary_lower = summary.lower()

        # Check for root categories
        root_category_map = {
            "physical": RootCategory.PHYSICAL,
            "mental": RootCategory.MENTAL,
            "financial": RootCategory.FINANCIAL,
            "social": RootCategory.SOCIAL,
        }

        for name, category in root_category_map.items():
            if name in summary_lower:
                categories["root_categories"].append(category.value)

        # Check for subcategories (from config)
        for subcat_name in settings.subcategories.keys():
            if subcat_name.lower() in summary_lower:
                categories["subcategories"].append(subcat_name)

        return categories

    def _determine_note_path(
        self,
        source_record: SourceRecord,
        relevant_notes: List[NoteRecord],
    ) -> Path:
        """Determine appropriate path for the summary note."""
        # Try to use same domain folder as most relevant note
        domain_folder = "sources"
        if relevant_notes:
            # Count domain folder occurrences
            domain_counts = {}
            for note in relevant_notes[:3]:  # Top 3 most relevant
                domain = note.domain_folder
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

            if domain_counts:
                domain_folder = max(domain_counts.items(), key=lambda x: x[1])[0]

        # Create safe filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in source_record.title)
        safe_title = safe_title[:100]  # Limit length

        filename = f"{safe_title}.md"

        # Build path
        vault_root = self.wiki_repo.vault_path
        note_path = vault_root / domain_folder / "source_summaries" / filename

        # Ensure directory exists
        note_path.parent.mkdir(parents=True, exist_ok=True)

        return note_path

    def batch_ingest(
        self,
        source_paths: List[str],
        source_type: str = "article",
        dry_run: bool = False,
    ) -> List[Tuple[SourceRecord, str]]:
        """Ingest multiple sources."""
        results = []

        for i, source_path in enumerate(source_paths):
            logger.info(f"Processing source {i + 1}/{len(source_paths)}: {source_path}")

            try:
                result = self.ingest_source(
                    source_path=source_path,
                    source_type=source_type,
                    dry_run=dry_run,
                )

                if result:
                    source_record, note_content = result
                    results.append((source_record, note_content))

                    if not dry_run:
                        logger.info(f"Successfully ingested: {source_record.title}")
                    else:
                        logger.info(f"Would ingest: {source_record.title}")
                else:
                    logger.error(f"Failed to ingest: {source_path}")

            except Exception as e:
                logger.error(f"Error ingesting {source_path}: {e}")

        return results


def run_ingest(
    source: str,
    source_type: Optional[str] = None,
    domain: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, any]:
    """Run wiki ingest workflow."""
    # Start audit log
    audit = AuditLogger()
    run_id = audit.start_run(command="wiki_ingest", mode="dry-run" if dry_run else "live")

    start_time = time.time()

    try:
        logger.info(f"Starting wiki ingest workflow: {source}")

        # Initialize workflow
        workflow = WikiIngestWorkflow()

        # Ingest source
        result = workflow.ingest_source(
            source_path=source,
            source_type=source_type or "article",
            dry_run=dry_run,
        )

        if not result:
            error_msg = f"Failed to ingest source: {source}"
            logger.error(error_msg)
            audit.log_error(run_id, error_msg)
            audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
            return {"error": error_msg}

        source_record, note_content = result

        # Prepare response
        response = {
            "source_title": source_record.title,
            "source_type": source_record.source_type,
            "source_location": source_record.source_location,
            "summary_note_path": str(source_record.summary_note_path)
            if source_record.summary_note_path
            else None,
            "ingested_at": source_record.ingested_at.isoformat()
            if source_record.ingested_at
            else None,
            "pages_to_update": [],  # Could be populated from LLM analysis
        }

        # Update audit log
        audit.update_run(
            run_id,
            status="running",
            notes_written=1 if source_record.summary_note_path and not dry_run else 0,
        )

        # Complete audit log
        duration = time.time() - start_time
        audit.complete_run(run_id, status="success", duration_seconds=duration)

        logger.info(f"Ingest completed in {duration:.2f} seconds")
        return response

    except Exception as e:
        logger.error(f"Ingest workflow failed: {e}")
        audit.log_error(run_id, str(e))
        audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
        raise


def batch_ingest(
    sources: List[str],
    source_type: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, any]:
    """Batch ingest multiple sources."""
    # Start audit log
    audit = AuditLogger()
    run_id = audit.start_run(command="wiki_ingest_batch", mode="dry-run" if dry_run else "live")

    start_time = time.time()

    try:
        logger.info(f"Starting batch ingest for {len(sources)} sources")

        # Initialize workflow
        workflow = WikiIngestWorkflow()

        # Ingest sources
        results = workflow.batch_ingest(
            source_paths=sources,
            source_type=source_type or "article",
            dry_run=dry_run,
        )

        # Prepare response
        response = {
            "total_sources": len(sources),
            "successful_ingests": len(results),
            "failed_ingests": len(sources) - len(results),
            "ingested_sources": [],
        }

        for source_record, note_content in results:
            response["ingested_sources"].append(
                {
                    "title": source_record.title,
                    "type": source_record.source_type,
                    "location": source_record.source_location,
                    "note_path": str(source_record.summary_note_path)
                    if source_record.summary_note_path
                    else None,
                }
            )

        # Update audit log
        audit.update_run(
            run_id,
            status="running",
            notes_written=len(results) if not dry_run else 0,
        )

        # Complete audit log
        duration = time.time() - start_time
        audit.complete_run(run_id, status="success", duration_seconds=duration)

        logger.info(f"Batch ingest completed in {duration:.2f} seconds")
        return response

    except Exception as e:
        logger.error(f"Batch ingest workflow failed: {e}")
        audit.log_error(run_id, str(e))
        audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
        raise


def main():
    """Main entry point for wiki ingest workflow."""
    import argparse

    parser = argparse.ArgumentParser(description="Ingest sources into your personal wiki")
    parser.add_argument(
        "sources",
        nargs="+",
        help="Source files or URLs to ingest",
    )
    parser.add_argument(
        "--type",
        default="article",
        choices=["article", "paper", "book", "podcast", "video", "data", "receipt"],
        help="Type of source (default: article)",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        help="Path to Obsidian vault (default: from settings)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to save summary notes (default: vault/sources/source_summaries)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize workflow
    workflow = WikiIngestWorkflow(vault_path=args.vault)

    # Ingest sources
    results = workflow.batch_ingest(
        source_paths=args.sources,
        source_type=args.type,
        dry_run=args.dry_run,
    )

    # Print results
    print(f"\nIngested {len(results)}/{len(args.sources)} sources:")
    print("=" * 60)

    for source_record, note_content in results:
        print(f"\nSource: {source_record.title}")
        print(f"Type: {source_record.source_type}")
        print(f"Location: {source_record.source_location}")

        if source_record.summary_note_path:
            print(f"Note: {source_record.summary_note_path}")

        if args.dry_run:
            print("Status: Dry run - note not created")
            print("\nNote content preview:")
            print("-" * 40)
            print(note_content[:500] + "..." if len(note_content) > 500 else note_content)
            print("-" * 40)
        else:
            print("Status: Successfully ingested")

        print()


if __name__ == "__main__":
    main()

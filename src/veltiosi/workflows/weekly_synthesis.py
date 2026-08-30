"""Weekly synthesis workflow for generating insights from wiki activity."""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..audit import AuditLogger
from ..models import NoteRecord, NoteType
from ..services.llm_service import llm_service
from ..services.wiki_repository import WikiRepository
from ..settings import settings

logger = logging.getLogger(__name__)


class WeeklySynthesisWorkflow:
    """Workflow for generating weekly synthesis notes."""

    def __init__(self, vault_path: Optional[Path] = None):
        """Initialize weekly synthesis workflow."""
        self.wiki_repo = WikiRepository(vault_path)

    def generate_synthesis(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        dry_run: bool = False,
    ) -> Optional[Tuple[str, str]]:
        """Generate weekly synthesis note."""
        from datetime import timezone

        # Default to last 7 days
        if end_date is None:
            end_date = datetime.now(tz=timezone.utc)
        elif end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        if start_date is None:
            start_date = end_date - timedelta(days=7)
        elif start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        logger.info(f"Generating synthesis for {start_date.date()} to {end_date.date()}")

        # Get wiki activity for the period
        activity = self._get_wiki_activity(start_date, end_date)

        if not any(activity.values()):
            logger.warning("No wiki activity found for the period")
            return None

        # Generate synthesis using LLM
        synthesis_content = llm_service.generate_weekly_synthesis(
            completed_tasks=activity["completed_tasks"],
            updated_pages=activity["updated_pages"],
            new_sources=activity["new_sources"],
            category_points=activity["category_points"],
        )

        if not synthesis_content:
            logger.error("Failed to generate synthesis content")
            return None

        # Create note content
        note_content = self._create_note_content(
            start_date=start_date,
            end_date=end_date,
            activity=activity,
            synthesis_content=synthesis_content,
        )

        # Determine note path
        note_path = self._determine_note_path(start_date, end_date)

        if not dry_run:
            # Save the note
            success = self.wiki_repo.write_note(note_path, note_content)
            if success:
                logger.info(f"Created synthesis note at: {note_path}")
                return note_path, note_content
            else:
                logger.error(f"Failed to write note to: {note_path}")
                return None
        else:
            logger.info(f"Dry run - would create note at: {note_path}")
            return note_path, note_content

    def _get_wiki_activity(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, List[str]]:
        """Get wiki activity for the given period."""
        activity = {
            "completed_tasks": [],
            "updated_pages": [],
            "new_sources": [],
            "category_points": {},
        }

        try:
            # Scan all notes
            all_notes = self.wiki_repo.scan_and_classify()

            for note in all_notes:
                # Check if note was modified in the period
                if note.modified_at:
                    # Normalise to UTC-aware for comparison
                    from datetime import timezone as _tz

                    note_time = (
                        note.modified_at
                        if note.modified_at.tzinfo
                        else note.modified_at.replace(tzinfo=_tz.utc)
                    )
                    if start_date <= note_time <= end_date:
                        # Categorize by note type
                        if note.note_type == NoteType.TASK_LINKED:
                            activity["completed_tasks"].append(note.title)
                        elif note.note_type == NoteType.SOURCE_SUMMARY:
                            activity["new_sources"].append(note.title)
                        else:
                            activity["updated_pages"].append(note.title)

                        # Add category points
                        if note.primary_root_category:
                            category = note.primary_root_category.value
                            activity["category_points"][category] = (
                                activity["category_points"].get(category, 0) + 1
                            )

                        for subcat in note.subcategories:
                            activity["category_points"][subcat] = (
                                activity["category_points"].get(subcat, 0) + 1
                            )

            # Sort category points by count
            activity["category_points"] = dict(
                sorted(activity["category_points"].items(), key=lambda x: x[1], reverse=True)
            )

            logger.info(
                f"Found {len(activity['updated_pages'])} updated pages, "
                f"{len(activity['completed_tasks'])} completed tasks, "
                f"{len(activity['new_sources'])} new sources"
            )

        except Exception as e:
            logger.error(f"Error getting wiki activity: {e}")

        return activity

    def _create_note_content(
        self,
        start_date: datetime,
        end_date: datetime,
        activity: Dict[str, List[str]],
        synthesis_content: str,
    ) -> str:
        """Create note content from synthesis."""
        # Format dates
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        period_str = f"{start_str} to {end_str}"

        # Build note content
        lines = [
            f"# Weekly Synthesis: {period_str}",
            "",
            "## Activity Summary",
            "",
        ]

        # Add activity counts
        lines.append(f"- **Updated Pages:** {len(activity['updated_pages'])}")
        lines.append(f"- **Completed Tasks:** {len(activity['completed_tasks'])}")
        lines.append(f"- **New Sources:** {len(activity['new_sources'])}")
        lines.append("")

        # Add category points
        if activity["category_points"]:
            lines.append("### Category Points")
            lines.append("")
            for category, points in list(activity["category_points"].items())[:10]:  # Top 10
                lines.append(f"- {category}: {points} points")
            lines.append("")

        # Add detailed activity if available
        if activity["completed_tasks"]:
            lines.extend(
                [
                    "### Completed Tasks",
                    "",
                ]
            )
            for task in activity["completed_tasks"][:20]:  # Limit to 20
                lines.append(f"- {task}")
            lines.append("")

        if activity["new_sources"]:
            lines.extend(
                [
                    "### New Sources",
                    "",
                ]
            )
            for source in activity["new_sources"][:10]:  # Limit to 10
                lines.append(f"- {source}")
            lines.append("")

        # Add LLM synthesis
        lines.extend(
            [
                "## AI Synthesis",
                "",
                synthesis_content,
                "",
            ]
        )

        # Add insights and action items
        lines.extend(
            [
                "## Key Insights",
                "",
                "*Extracted from the synthesis above:*",
                "",
                "1. **Growth Areas:** ",
                "2. **Knowledge Gaps:** ",
                "3. **Emerging Patterns:** ",
                "4. **Action Items:** ",
                "",
            ]
        )

        # Add metadata
        lines.extend(
            [
                "## Metadata",
                "",
                f"- **Period:** {period_str}",
                f"- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"- **Total Notes Processed:** {sum(len(v) for v in activity.values() if isinstance(v, list))}",
                "",
                "---",
                f"*Generated by Veltiosi weekly synthesis workflow*",
            ]
        )

        return "\n".join(lines)

    def _determine_note_path(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Path:
        """Determine path for synthesis note."""
        # Format filename
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        filename = f"Weekly Synthesis {start_str}-{end_str}.md"

        # Build path
        vault_root = self.wiki_repo.vault_path
        note_path = vault_root / "synthesis" / "weekly" / filename

        # Ensure directory exists
        note_path.parent.mkdir(parents=True, exist_ok=True)

        return note_path

    def generate_retrospective(
        self,
        weeks: int = 4,
        dry_run: bool = False,
    ) -> Optional[List[Tuple[str, str]]]:
        """Generate synthesis for multiple weeks."""
        results = []
        end_date = datetime.now()

        for week in range(weeks):
            week_end = end_date - timedelta(days=week * 7)
            week_start = week_end - timedelta(days=7)

            logger.info(
                f"Generating synthesis for week {week + 1}: "
                f"{week_start.date()} to {week_end.date()}"
            )

            result = self.generate_synthesis(
                start_date=week_start,
                end_date=week_end,
                dry_run=dry_run,
            )

            if result:
                note_path, note_content = result
                results.append((note_path, note_content))

        return results


def run_weekly_synthesis(
    week: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, any]:
    """Run weekly synthesis workflow."""
    # Start audit log
    audit = AuditLogger()
    run_id = audit.start_run(command="weekly_synthesis", mode="dry-run" if dry_run else "live")

    start_time = time.time()

    try:
        logger.info("Starting weekly synthesis workflow")

        # Initialize workflow
        workflow = WeeklySynthesisWorkflow()

        # Parse week if provided
        start_date = None
        end_date = None

        if week:
            # Parse YYYY-WW format
            try:
                year, week_num = map(int, week.split("-"))
                # Simple approximation - could be more accurate
                start_date = datetime(year, 1, 1) + timedelta(weeks=week_num - 1)
                end_date = start_date + timedelta(days=6)
            except ValueError:
                logger.warning(f"Invalid week format: {week}, using default")

        # Generate synthesis
        result = workflow.generate_synthesis(
            start_date=start_date,
            end_date=end_date,
            dry_run=dry_run,
        )

        if not result:
            error_msg = "Failed to generate weekly synthesis"
            logger.error(error_msg)
            audit.log_error(run_id, error_msg)
            audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
            return {"error": error_msg}

        note_path, note_content = result

        # Prepare response
        response = {
            "output_path": str(note_path),
            "week": week or "current",
            "category_balance": {},  # Could be populated from analysis
            "gaps": [],  # Could be populated from analysis
            "suggested_next_tasks": [],  # Could be populated from analysis
        }

        # Update audit log
        audit.update_run(
            run_id,
            status="running",
            notes_written=1 if not dry_run else 0,
        )

        # Complete audit log
        duration = time.time() - start_time
        audit.complete_run(run_id, status="success", duration_seconds=duration)

        logger.info(f"Weekly synthesis completed in {duration:.2f} seconds")
        return response

    except Exception as e:
        logger.error(f"Weekly synthesis workflow failed: {e}")
        audit.log_error(run_id, str(e))
        audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
        raise


def run_retrospective(
    weeks: int = 4,
    dry_run: bool = False,
) -> Dict[str, any]:
    """Run retrospective synthesis for multiple weeks."""
    # Start audit log
    audit = AuditLogger()
    run_id = audit.start_run(
        command="weekly_synthesis_retrospective", mode="dry-run" if dry_run else "live"
    )

    start_time = time.time()

    try:
        logger.info(f"Starting retrospective synthesis for {weeks} weeks")

        # Initialize workflow
        workflow = WeeklySynthesisWorkflow()

        # Generate retrospective
        results = workflow.generate_retrospective(
            weeks=weeks,
            dry_run=dry_run,
        )

        # Prepare response
        response = {
            "weeks_generated": len(results),
            "notes_created": [],
            "total_weeks": weeks,
        }

        for note_path, note_content in results:
            response["notes_created"].append(
                {
                    "path": str(note_path),
                    "content_preview": note_content[:200] + "..."
                    if len(note_content) > 200
                    else note_content,
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

        logger.info(f"Retrospective synthesis completed in {duration:.2f} seconds")
        return response

    except Exception as e:
        logger.error(f"Retrospective synthesis workflow failed: {e}")
        audit.log_error(run_id, str(e))
        audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
        raise


def main():
    """Main entry point for weekly synthesis workflow."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate weekly synthesis notes")
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
        help="Start date (YYYY-MM-DD, default: 7 days ago)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
        help="End date (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=1,
        help="Number of weeks to generate synthesis for (default: 1)",
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
        "--retrospective",
        action="store_true",
        help="Generate synthesis for multiple weeks",
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
    workflow = WeeklySynthesisWorkflow(vault_path=args.vault)

    # Generate synthesis
    if args.retrospective:
        results = workflow.generate_retrospective(
            weeks=args.weeks,
            dry_run=args.dry_run,
        )

        if results:
            print(f"\nGenerated {len(results)} synthesis notes:")
            print("=" * 60)

            for note_path, note_content in results:
                print(f"\nNote: {note_path}")

                if args.dry_run:
                    print("Status: Dry run - note not created")
                    print("\nContent preview:")
                    print("-" * 40)
                    print(note_content[:500] + "..." if len(note_content) > 500 else note_content)
                    print("-" * 40)
                else:
                    print("Status: Successfully created")

                print()
        else:
            print("No synthesis notes generated.")

    else:
        result = workflow.generate_synthesis(
            start_date=args.start_date,
            end_date=args.end_date,
            dry_run=args.dry_run,
        )

        if result:
            note_path, note_content = result

            print(f"\nGenerated synthesis note:")
            print("=" * 60)
            print(f"Path: {note_path}")

            if args.dry_run:
                print("Status: Dry run - note not created")
                print("\nFull content:")
                print("=" * 60)
                print(note_content)
                print("=" * 60)
            else:
                print("Status: Successfully created")
                print("\nContent preview:")
                print("-" * 40)
                print(note_content[:1000] + "..." if len(note_content) > 1000 else note_content)
                print("-" * 40)
        else:
            print("Failed to generate synthesis note.")


if __name__ == "__main__":
    main()

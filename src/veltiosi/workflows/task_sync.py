"""Task synchronization workflow."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..audit import AuditLogger
from ..connectors.atma import AtmaConnector
from ..services.wiki_repository import WikiRepository
from ..models import TaskMappingResult

logger = logging.getLogger(__name__)


def run_task_sync(
    days: int = 7,
    task_id: Optional[int] = None,
    dry_run: bool = False,
    auto_apply_threshold: float = 0.7,
) -> Dict[str, any]:
    """Run task synchronization workflow."""
    # Start audit log
    audit = AuditLogger()
    run_id = audit.start_run(command="task_sync", mode="dry-run" if dry_run else "live")

    start_time = time.time()

    try:
        logger.info("Starting task synchronization workflow")

        # Initialize components
        atma_connector = AtmaConnector()
        wiki_repo = WikiRepository()

        # Step 1: Get tasks from Atma
        logger.info("Step 1: Fetching tasks from Atma...")

        if task_id:
            # For single task sync, we need to implement get_task_by_id
            # For now, we'll use get_recent_tasks and filter
            tasks = atma_connector.get_recent_tasks(days_back=days, status="completed")
            tasks = [t for t in tasks if t.id == task_id]
            if not tasks:
                error_msg = f"Task {task_id} not found in recent completed tasks"
                logger.error(error_msg)
                audit.log_error(run_id, error_msg)
                audit.complete_run(run_id, status="failure")
                return {"error": error_msg}
        else:
            tasks = atma_connector.get_recent_tasks(days_back=days, status="completed")

        if not tasks:
            logger.info("No completed tasks found in the specified time period")
            audit.complete_run(run_id, status="success", duration_seconds=time.time() - start_time)
            return {
                "tasks_processed": 0,
                "auto_applied": 0,
                "review_items_created": 0,
                "skipped": 0,
                "review_queue_items": [],
            }

        logger.info(f"Found {len(tasks)} completed tasks")

        # Step 2: Map tasks to wiki
        logger.info("Step 2: Mapping tasks to wiki categories...")
        mapping_results = atma_connector.batch_map_tasks(tasks, auto_apply_threshold)

        auto_apply_tasks = mapping_results["auto_apply"]
        review_queue_tasks = mapping_results["review_queue"]
        skipped_tasks = mapping_results["skip"]

        logger.info(
            f"Task mapping: {len(auto_apply_tasks)} auto-apply, "
            f"{len(review_queue_tasks)} review, {len(skipped_tasks)} skip"
        )

        # Step 3: Process auto-apply tasks
        auto_applied_count = 0
        processed_task_ids = []

        if auto_apply_tasks and not dry_run:
            logger.info("Step 3: Processing auto-apply tasks...")

            for mapping in auto_apply_tasks:
                task = next((t for t in tasks if t.id == mapping["task_id"]), None)
                if not task:
                    continue

                try:
                    # Update wiki with task completion
                    note_path = _update_wiki_with_task(
                        task=task,
                        mapping=mapping,
                        wiki_repo=wiki_repo,
                        dry_run=dry_run,
                    )

                    # Mark task as processed in Atma
                    if note_path:
                        atma_connector.mark_task_as_processed(task, mapping, str(note_path))
                    else:
                        atma_connector.mark_task_as_processed(task, mapping)

                    auto_applied_count += 1
                    processed_task_ids.append(task.id)
                    logger.info(f"Auto-applied task {task.id}: {task.title}")

                except Exception as e:
                    logger.error(f"Failed to process auto-apply task {task.id}: {e}")
                    audit.log_error(run_id, f"Failed to process task {task.id}: {e}")

        # Step 4: Create review queue items
        review_items_created = 0
        review_queue_items = []

        if review_queue_tasks and not dry_run:
            logger.info("Step 4: Creating review queue items...")

            for mapping in review_queue_tasks:
                task = next((t for t in tasks if t.id == mapping["task_id"]), None)
                if not task:
                    continue

                try:
                    review_item_path = _create_review_queue_item(
                        task=task,
                        mapping=mapping,
                        wiki_repo=wiki_repo,
                    )

                    if review_item_path:
                        review_items_created += 1
                        review_queue_items.append(str(review_item_path))
                        logger.info(f"Created review queue item for task {task.id}")

                except Exception as e:
                    logger.error(f"Failed to create review queue item for task {task.id}: {e}")
                    audit.log_error(run_id, f"Failed to create review item for task {task.id}: {e}")

        # Step 5: Log skipped tasks
        if skipped_tasks:
            logger.info(f"Skipped {len(skipped_tasks)} tasks (low confidence)")
            for mapping in skipped_tasks:
                task = next((t for t in tasks if t.id == mapping["task_id"]), None)
                if task:
                    logger.debug(
                        f"Skipped task {task.id}: {task.title} (confidence: {mapping['confidence']:.2f})"
                    )

        # Update audit log
        audit.update_run(
            run_id,
            status="running",
            tasks_processed=processed_task_ids,
            review_items_created=review_items_created,
        )

        # Complete audit log
        duration = time.time() - start_time
        audit.complete_run(run_id, status="success", duration_seconds=duration)

        logger.info(f"Task sync completed in {duration:.2f} seconds")

        return {
            "tasks_processed": len(tasks),
            "auto_applied": auto_applied_count,
            "review_items_created": review_items_created,
            "skipped": len(skipped_tasks),
            "review_queue_items": review_queue_items,
        }

    except Exception as e:
        logger.error(f"Task sync workflow failed: {e}")
        audit.log_error(run_id, str(e))
        audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
        raise


def _update_wiki_with_task(
    task,
    mapping: TaskMappingResult,
    wiki_repo: WikiRepository,
    dry_run: bool = False,
) -> Optional[Path]:
    """Update wiki with task completion."""

    # Get target page path
    target_page = mapping.get("target_page")
    if not target_page:
        # If no specific target page, use category-based page
        category = mapping.get("category")
        if not category:
            logger.warning(f"No category for task {task.id}, cannot update wiki")
            return None

        # Determine page name based on category
        # This should be enhanced with proper page naming logic
        page_name = f"{category.title()} Progress"
        target_page = f"20-Task-System/Compounding-Pages/{page_name}.md"

    # Check if page exists
    page_path = wiki_repo.vault_path / target_page
    if not page_path.exists():
        logger.info(f"Creating new compounding page: {target_page}")

        # Create page with basic structure
        content = f"""# {page_name}

## Task Completions

### {datetime.now().strftime("%Y-%m-%d")}
- **{task.title}** (completed: {task.completed_at.strftime("%Y-%m-%d") if task.completed_at else "N/A"})
  {task.description or ""}

## Slope Analysis
*What's changing?*

## Key Insights

## Next Actions
"""

        if not dry_run:
            wiki_repo.write_note(page_path, content)
        else:
            logger.info(f"[DRY RUN] Would create page: {page_path}")
    else:
        # Update existing page
        logger.info(f"Updating existing page: {target_page}")

        # Read existing content
        content = page_path.read_text()

        # Find or create today's date section
        today_header = f"### {datetime.now().strftime('%Y-%m-%d')}"
        task_entry = f"- **{task.title}** (completed: {task.completed_at.strftime('%Y-%m-%d') if task.completed_at else 'N/A'})\n  {task.description or ''}"

        # Deduplication guard: skip if exact entry already exists
        if task_entry in content:
            logger.info(f"Task {task.id} already in page, skipping duplicate")
            return page_path

        if today_header in content:
            # Insert task under today's header
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.strip() == today_header:
                    # Insert task after the header
                    lines.insert(i + 1, task_entry)
                    break
            content = "\n".join(lines)
        else:
            # Add new date section after "Task Completions" header
            task_completions_header = "## Task Completions"
            if task_completions_header in content:
                insert_index = content.find(task_completions_header) + len(task_completions_header)
                new_content = (
                    content[:insert_index]
                    + f"\n\n{today_header}\n{task_entry}\n"
                    + content[insert_index:]
                )
                content = new_content
            else:
                # Add both headers
                content = f"{content}\n\n## Task Completions\n\n{today_header}\n{task_entry}\n"

        if not dry_run:
            wiki_repo.write_note(page_path, content)
        else:
            logger.info(f"[DRY RUN] Would update page: {page_path}")

    return page_path


def _create_review_queue_item(
    task,
    mapping: TaskMappingResult,
    wiki_repo: WikiRepository,
) -> Optional[Path]:
    """Create a review queue item for ambiguous task mapping."""

    # Generate queue ID
    queue_id = f"task_{task.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    review_file_path = f"20-Task-System/Review-Queue/{queue_id}.md"

    # Create review content
    content = f"""# Review Queue: Task {task.id}

**Status:** pending  
**Task ID:** {task.id}  
**Task Title:** {task.title}  
**Completed:** {task.completed_at.strftime("%Y-%m-%d %H:%M:%S") if task.completed_at else "N/A"}  
**Created:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Ambiguity Reason
Confidence score: {mapping["confidence"]:.2f} (threshold: 0.7)

The task mapping system wasn't confident enough to auto-apply this task to the wiki.

## Proposed Mapping
- **Category:** {mapping.get("category", "N/A")}
- **Subcategories:** {", ".join(mapping.get("subcategories", []))}
- **Tags:** {", ".join(mapping.get("tags", []))}
- **Target Page:** {mapping.get("target_page", "N/A")}

## Task Details
**Title:** {task.title}

**Description:**
{task.description or "No description provided"}

**Tags:** {", ".join(task.tags)}

## Candidate Wiki Pages
Consider linking this task to one of these pages:

1. **Option 1:** Create new compounding page for category "{mapping.get("category", "N/A")}"
2. **Option 2:** Add to existing relevant page (search vault for related topics)
3. **Option 3:** Skip this task (if not relevant for wiki)

## Resolution
- [ ] **Approve** - Use proposed mapping
- [ ] **Modify** - Use different mapping
- [ ] **Deny** - Skip this task

**Notes:**
<!-- Add any notes about your decision here -->

## Action Taken
<!-- Fill this in after resolution -->
- [ ] Task applied to wiki
- [ ] Task skipped
- [ ] Other: 

**Resolution Date:**  
**Resolved By:**  
**Notes:**
"""

    try:
        page_path = wiki_repo.vault_path / review_file_path
        wiki_repo.write_note(page_path, content)
        logger.info(f"Created review queue item: {review_file_path}")
        return page_path
    except Exception as e:
        logger.error(f"Failed to create review queue item: {e}")
        return None

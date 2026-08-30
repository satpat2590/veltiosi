"""Atma task management connector."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel, Field

from ..models import TaskMappingResult
from ..settings import settings

logger = logging.getLogger(__name__)


class AtmaTask(BaseModel):
    """Atma task model."""

    id: int
    completion_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: str
    priority: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AtmaConnector:
    """Connector for Atma task management system."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize Atma connector."""
        self.base_url = base_url or settings.atma_base_url
        self.api_key = api_key or settings.atma_api_key
        self.session = requests.Session()

        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

        if not self.base_url:
            logger.warning("Atma base URL not configured")

    def get_recent_tasks(
        self, days_back: int = 7, status: str = "completed", limit: int = 50
    ) -> List[AtmaTask]:
        """Get recent completed tasks from Atma via the /api/completed endpoint."""
        if not self.base_url:
            logger.error("Atma base URL not configured")
            return []

        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

            params = {
                "since": cutoff_date.isoformat(),
                "limit": limit,
            }

            response = self.session.get(f"{self.base_url}/api/completed", params=params, timeout=30)
            response.raise_for_status()

            completions_data = response.json()
            tasks = []

            # Handle both list response and dict with "completions" key
            if isinstance(completions_data, list):
                completion_list = completions_data
            else:
                completion_list = completions_data.get("completions", [])

            for completion_data in completion_list:
                try:
                    # Map completion record to AtmaTask model
                    completed_at_str = completion_data.get("completed_at")
                    completed_at = datetime.fromisoformat(completed_at_str.replace("Z", "+00:00")) if completed_at_str else None

                    # Client-side filtering: skip completions older than cutoff
                    if completed_at and completed_at < cutoff_date:
                        continue

                    task = AtmaTask(
                        id=completion_data["task_id"],
                        completion_id=completion_data["id"],
                        title=completion_data.get("task_title", "Unknown"),
                        description=None,
                        status="completed",
                        priority=None,
                        tags=[],
                        created_at=completed_at or datetime.now(),
                        completed_at=completed_at,
                        due_date=None,
                        metadata={
                            "category": completion_data.get("task_category"),
                            "was_late": completion_data.get("was_late"),
                            "time_spent_minutes": completion_data.get("time_spent_minutes"),
                            "points": completion_data.get("points"),
                            "completion_notes": completion_data.get("notes"),
                        },
                    )
                    tasks.append(task)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse completion {completion_data.get('id')}: {e}")
                    continue

            logger.info(f"Retrieved {len(tasks)} completed tasks from Atma")
            return tasks

        except requests.RequestException as e:
            logger.error(f"Failed to fetch completed tasks from Atma: {e}")
            return []

    def map_task_to_wiki(
        self, task: AtmaTask, confidence_threshold: float = 0.7
    ) -> TaskMappingResult:
        """Map a task to wiki categories and pages."""
        from ..utils.text import extract_keywords, calculate_similarity

        # Extract keywords from task title and description
        task_text = f"{task.title} {task.description or ''}"
        keywords = extract_keywords(task_text)

        # Apply task rules
        best_match = None
        best_confidence = 0.0

        for rule in settings.task_rules:
            # Check if any rule pattern matches
            for pattern in rule.match_any:
                if pattern.lower() in task_text.lower():
                    confidence = rule.confidence

                    # Boost confidence if tags match
                    if any(tag in task.tags for tag in rule.tags):
                        confidence = min(1.0, confidence + 0.2)

                    if confidence > best_confidence:
                        best_match = rule
                        best_confidence = confidence

        # Determine decision based on confidence
        if best_confidence >= confidence_threshold:
            decision = "auto_apply"
        elif best_confidence >= 0.3:  # Medium confidence - needs review
            decision = "review_queue"
        else:
            decision = "skip"

        # Build result
        result = TaskMappingResult(
            task_id=task.id,
            confidence=best_confidence,
            category=best_match.category if best_match else None,
            subcategories=best_match.subcategories if best_match else [],
            tags=best_match.tags if best_match else [],
            target_page=best_match.target_page if best_match else None,
            decision=decision,
        )

        return result

    def batch_map_tasks(
        self, tasks: List[AtmaTask], auto_apply_threshold: float = 0.7
    ) -> Dict[str, List[TaskMappingResult]]:
        """Batch map multiple tasks to wiki."""
        results = {"auto_apply": [], "review_queue": [], "skip": []}

        for task in tasks:
            mapping = self.map_task_to_wiki(task, auto_apply_threshold)
            results[mapping["decision"]].append(mapping)

        logger.info(
            f"Task mapping complete: {len(results['auto_apply'])} auto-apply, "
            f"{len(results['review_queue'])} review, {len(results['skip'])} skip"
        )

        return results

    def mark_task_as_processed(
        self, task: AtmaTask, mapping_result: TaskMappingResult, note_path: Optional[str] = None
    ) -> bool:
        """Mark a task completion as processed in Atma by updating completion notes."""
        if not self.base_url:
            logger.warning("Atma base URL not configured, skipping task update")
            return False

        if not task.completion_id:
            logger.warning(f"Task {task.id} has no completion_id, cannot mark as processed")
            return False

        try:
            # Build sync annotation to append to existing notes
            existing_notes = task.metadata.get("completion_notes", "") or ""

            # Idempotency: skip if already marked as processed by veltiosi
            if "[veltiosi-synced" in existing_notes:
                logger.info(f"Task {task.id} (completion {task.completion_id}) already marked as processed")
                return True

            sync_note = f"\n[veltiosi-synced {datetime.now().isoformat()}]"
            if mapping_result.get("category"):
                sync_note += f" category={mapping_result['category']}"
            if note_path:
                sync_note += f" note={note_path}"

            new_notes = existing_notes + sync_note

            update_data = {"notes": new_notes}

            response = self.session.patch(
                f"{self.base_url}/api/completed/{task.completion_id}", json=update_data, timeout=30
            )
            response.raise_for_status()

            logger.info(f"Marked task {task.id} (completion {task.completion_id}) as processed")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to mark task {task.id} as processed: {e}")
            return False

    def test_connection(self) -> bool:
        """Test connection to Atma API."""
        if not self.base_url:
            logger.error("Atma base URL not configured")
            return False

        try:
            response = self.session.get(f"{self.base_url}/api/health", timeout=10)
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Atma connection test failed: {e}")
            return False

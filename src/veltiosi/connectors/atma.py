"""Atma task management connector."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel, Field

from ..models import TaskMappingResult
from ..settings import settings

logger = logging.getLogger(__name__)


class AtmaTask(BaseModel):
    """Atma task model."""

    id: int
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
        """Get recent tasks from Atma."""
        if not self.base_url:
            logger.error("Atma base URL not configured")
            return []

        try:
            cutoff_date = datetime.now() - timedelta(days=days_back)

            params = {
                "status": status,
                "since": cutoff_date.isoformat(),
                "limit": limit,
                "order_by": "completed_at",
                "order_dir": "desc",
            }

            response = self.session.get(f"{self.base_url}/api/tasks", params=params, timeout=30)
            response.raise_for_status()

            tasks_data = response.json()
            tasks = []

            for task_data in tasks_data.get("tasks", []):
                try:
                    task = AtmaTask(
                        id=task_data["id"],
                        title=task_data["title"],
                        description=task_data.get("description"),
                        status=task_data["status"],
                        priority=task_data.get("priority"),
                        tags=task_data.get("tags", []),
                        created_at=datetime.fromisoformat(task_data["created_at"]),
                        completed_at=datetime.fromisoformat(task_data["completed_at"])
                        if task_data.get("completed_at")
                        else None,
                        due_date=datetime.fromisoformat(task_data["due_date"])
                        if task_data.get("due_date")
                        else None,
                        metadata=task_data.get("metadata", {}),
                    )
                    tasks.append(task)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse task {task_data.get('id')}: {e}")
                    continue

            logger.info(f"Retrieved {len(tasks)} tasks from Atma")
            return tasks

        except requests.RequestException as e:
            logger.error(f"Failed to fetch tasks from Atma: {e}")
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
        self, task_id: int, mapping_result: TaskMappingResult, note_path: Optional[str] = None
    ) -> bool:
        """Mark a task as processed in Atma."""
        if not self.base_url:
            logger.warning("Atma base URL not configured, skipping task update")
            return False

        try:
            update_data = {
                "metadata": {
                    "veltiosi_processed": True,
                    "veltiosi_processed_at": datetime.now().isoformat(),
                    "veltiosi_mapping": {
                        "confidence": mapping_result["confidence"],
                        "category": mapping_result["category"],
                        "subcategories": mapping_result["subcategories"],
                        "tags": mapping_result["tags"],
                        "target_page": mapping_result["target_page"],
                        "decision": mapping_result["decision"],
                    },
                }
            }

            if note_path:
                update_data["metadata"]["veltiosi_note_path"] = note_path

            response = self.session.patch(
                f"{self.base_url}/api/tasks/{task_id}", json=update_data, timeout=30
            )
            response.raise_for_status()

            logger.info(f"Marked task {task_id} as processed")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to mark task {task_id} as processed: {e}")
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

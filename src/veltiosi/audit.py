"""Audit logging system."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AuditEvent, ReviewQueueItem
from .settings import settings

logger = logging.getLogger(__name__)


class AuditLogger:
    """Audit logging system for tracking operations."""

    def __init__(self, audit_dir: Optional[Path] = None):
        """Initialize audit logger."""
        self.audit_dir = audit_dir or settings.audit_dir or Path.home() / ".veltiosi" / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        self.events_dir = self.audit_dir / "events"
        self.review_queue_dir = self.audit_dir / "review_queue"
        self.reports_dir = self.audit_dir / "reports"

        for directory in [self.events_dir, self.review_queue_dir, self.reports_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        logger.info(f"Audit logger initialized with directory: {self.audit_dir}")

    def start_run(self, command: str, mode: str = "dry-run") -> str:
        """Start a new audit run and return run ID."""
        run_id = str(uuid.uuid4())[:8]

        event = AuditEvent(run_id=run_id, command=command, mode=mode, status="running")

        # Save initial event
        self._save_event(event)

        logger.info(f"Started audit run {run_id}: {command} ({mode})")
        return run_id

    def update_run(
        self,
        run_id: str,
        status: str,
        notes_read: Optional[int] = None,
        notes_written: Optional[int] = None,
        review_items_created: Optional[int] = None,
        tasks_processed: Optional[List[int]] = None,
        warnings: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
        duration_seconds: Optional[float] = None,
    ) -> bool:
        """Update an audit run."""
        event_file = self.events_dir / f"{run_id}.json"

        if not event_file.exists():
            logger.error(f"Audit run not found: {run_id}")
            return False

        try:
            with open(event_file, "r") as f:
                event_data = json.load(f)

            # Update fields
            event_data["status"] = status
            event_data["timestamp"] = datetime.now().isoformat()

            if notes_read is not None:
                event_data["notes_read"] = notes_read
            if notes_written is not None:
                event_data["notes_written"] = notes_written
            if review_items_created is not None:
                event_data["review_items_created"] = review_items_created
            if tasks_processed is not None:
                event_data["tasks_processed"] = tasks_processed
            if warnings is not None:
                event_data["warnings"] = warnings
            if errors is not None:
                event_data["errors"] = errors
            if duration_seconds is not None:
                event_data["duration_seconds"] = duration_seconds

            # Save updated event
            with open(event_file, "w") as f:
                json.dump(event_data, f, indent=2)

            logger.debug(f"Updated audit run {run_id}: {status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update audit run {run_id}: {e}")
            return False

    def complete_run(
        self, run_id: str, status: str = "success", duration_seconds: Optional[float] = None
    ) -> bool:
        """Complete an audit run."""
        return self.update_run(run_id=run_id, status=status, duration_seconds=duration_seconds)

    def log_warning(self, run_id: str, warning: str) -> bool:
        """Log a warning to an audit run."""
        event_file = self.events_dir / f"{run_id}.json"

        if not event_file.exists():
            logger.error(f"Audit run not found: {run_id}")
            return False

        try:
            with open(event_file, "r") as f:
                event_data = json.load(f)

            warnings = event_data.get("warnings", [])
            warnings.append(f"{datetime.now().isoformat()}: {warning}")
            event_data["warnings"] = warnings

            with open(event_file, "w") as f:
                json.dump(event_data, f, indent=2)

            logger.warning(f"Audit run {run_id}: {warning}")
            return True

        except Exception as e:
            logger.error(f"Failed to log warning for run {run_id}: {e}")
            return False

    def log_error(self, run_id: str, error: str) -> bool:
        """Log an error to an audit run."""
        event_file = self.events_dir / f"{run_id}.json"

        if not event_file.exists():
            logger.error(f"Audit run not found: {run_id}")
            return False

        try:
            with open(event_file, "r") as f:
                event_data = json.load(f)

            errors = event_data.get("errors", [])
            errors.append(f"{datetime.now().isoformat()}: {error}")
            event_data["errors"] = errors

            with open(event_file, "w") as f:
                json.dump(event_data, f, indent=2)

            logger.error(f"Audit run {run_id}: {error}")
            return True

        except Exception as e:
            logger.error(f"Failed to log error for run {run_id}: {e}")
            return False

    def add_to_review_queue(
        self,
        task_id: int,
        task_title: str,
        ambiguity_reason: str,
        proposed_mappings: List[Dict[str, Any]],
        candidate_pages: List[str],
    ) -> Optional[str]:
        """Add an item to the review queue."""
        queue_id = str(uuid.uuid4())[:8]

        item = ReviewQueueItem(
            queue_id=queue_id,
            status="pending",
            task_id=task_id,
            task_title=task_title,
            ambiguity_reason=ambiguity_reason,
            proposed_mappings=proposed_mappings,
            candidate_pages=candidate_pages,
        )

        try:
            item_file = self.review_queue_dir / f"{queue_id}.json"

            with open(item_file, "w") as f:
                json.dump(item.model_dump(), f, indent=2)

            logger.info(f"Added to review queue: {queue_id} (task {task_id})")
            return queue_id

        except Exception as e:
            logger.error(f"Failed to add to review queue: {e}")
            return None

    def get_review_queue(self, status: str = "pending") -> List[ReviewQueueItem]:
        """Get items from the review queue."""
        items = []

        try:
            for item_file in self.review_queue_dir.glob("*.json"):
                try:
                    with open(item_file, "r") as f:
                        item_data = json.load(f)

                    item = ReviewQueueItem(**item_data)

                    if item.status == status:
                        items.append(item)

                except Exception as e:
                    logger.warning(f"Failed to parse review queue item {item_file}: {e}")
                    continue

            return sorted(items, key=lambda x: x.created_at)

        except Exception as e:
            logger.error(f"Failed to get review queue: {e}")
            return []

    def update_review_item(
        self, queue_id: str, status: str, resolution_notes: Optional[str] = None
    ) -> bool:
        """Update a review queue item."""
        item_file = self.review_queue_dir / f"{queue_id}.json"

        if not item_file.exists():
            logger.error(f"Review item not found: {queue_id}")
            return False

        try:
            with open(item_file, "r") as f:
                item_data = json.load(f)

            item_data["status"] = status
            item_data["resolved_at"] = datetime.now().isoformat() if status != "pending" else None
            item_data["resolution_notes"] = resolution_notes

            with open(item_file, "w") as f:
                json.dump(item_data, f, indent=2)

            logger.info(f"Updated review item {queue_id}: {status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update review item {queue_id}: {e}")
            return False

    def generate_report(
        self,
        run_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Generate an audit report."""
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {},
            "events": [],
            "review_queue_stats": {},
            "recommendations": [],
        }

        # Collect events
        events = []
        for event_file in self.events_dir.glob("*.json"):
            try:
                with open(event_file, "r") as f:
                    event_data = json.load(f)

                event_time = datetime.fromisoformat(event_data["timestamp"])

                # Apply filters
                if run_id and event_data["run_id"] != run_id:
                    continue
                if start_date and event_time < start_date:
                    continue
                if end_date and event_time > end_date:
                    continue

                events.append(event_data)

            except Exception as e:
                logger.warning(f"Failed to parse event file {event_file}: {e}")
                continue

        # Sort events by timestamp
        events.sort(key=lambda x: x["timestamp"])

        # Calculate summary
        if events:
            report["summary"] = {
                "total_runs": len(events),
                "successful_runs": len([e for e in events if e["status"] == "success"]),
                "failed_runs": len([e for e in events if e["status"] == "failure"]),
                "partial_runs": len([e for e in events if e["status"] == "partial"]),
                "total_notes_read": sum(e.get("notes_read", 0) for e in events),
                "total_notes_written": sum(e.get("notes_written", 0) for e in events),
                "total_review_items": sum(e.get("review_items_created", 0) for e in events),
                "total_tasks_processed": sum(len(e.get("tasks_processed", [])) for e in events),
                "total_warnings": sum(len(e.get("warnings", [])) for e in events),
                "total_errors": sum(len(e.get("errors", [])) for e in events),
            }

        report["events"] = events

        # Review queue stats
        pending_items = self.get_review_queue("pending")
        resolved_items = self.get_review_queue("resolved")

        report["review_queue_stats"] = {
            "pending": len(pending_items),
            "resolved": len(resolved_items),
            "total": len(pending_items) + len(resolved_items),
            "oldest_pending": min([item.created_at for item in pending_items], default=None),
        }

        # Generate recommendations
        recommendations = []

        # Check for frequent errors
        error_counts = {}
        for event in events:
            for error in event.get("errors", []):
                error_key = error.split(":")[0] if ":" in error else error
                error_counts[error_key] = error_counts.get(error_key, 0) + 1

        for error, count in error_counts.items():
            if count >= 3:
                recommendations.append(
                    {
                        "type": "error_pattern",
                        "message": f"Frequent error: {error} ({count} occurrences)",
                        "suggestion": "Investigate and fix the root cause",
                        "priority": "high",
                    }
                )

        # Check review queue backlog
        if len(pending_items) > 10:
            recommendations.append(
                {
                    "type": "review_backlog",
                    "message": f"Large review queue backlog: {len(pending_items)} items pending",
                    "suggestion": "Process review queue items or adjust confidence thresholds",
                    "priority": "medium",
                }
            )

        # Check for failed runs
        failed_runs = [e for e in events if e["status"] == "failure"]
        if failed_runs:
            recommendations.append(
                {
                    "type": "failed_runs",
                    "message": f"{len(failed_runs)} failed runs detected",
                    "suggestion": "Review error logs and fix issues",
                    "priority": "high",
                }
            )

        report["recommendations"] = recommendations

        # Save report
        report_file = self.reports_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Generated audit report: {report_file}")
        return report

    def _save_event(self, event: AuditEvent) -> None:
        """Save an audit event to disk."""
        try:
            event_file = self.events_dir / f"{event.run_id}.json"

            # Convert model to dict with datetime serialization
            event_dict = event.model_dump()
            # Convert datetime objects to ISO format strings
            for key, value in event_dict.items():
                if isinstance(value, datetime):
                    event_dict[key] = value.isoformat()

            with open(event_file, "w") as f:
                json.dump(event_dict, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save audit event: {e}")

    def cleanup_old_events(self, days_to_keep: int = 30) -> int:
        """Clean up old audit events."""
        cutoff_date = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
        deleted_count = 0

        try:
            for event_file in self.events_dir.glob("*.json"):
                try:
                    file_mtime = event_file.stat().st_mtime
                    if file_mtime < cutoff_date:
                        event_file.unlink()
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete old event {event_file}: {e}")

            logger.info(f"Cleaned up {deleted_count} old audit events")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old events: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get audit system statistics."""
        return {
            "audit_dir": str(self.audit_dir),
            "total_events": len(list(self.events_dir.glob("*.json"))),
            "total_review_items": len(list(self.review_queue_dir.glob("*.json"))),
            "total_reports": len(list(self.reports_dir.glob("*.json"))),
            "pending_review_items": len(self.get_review_queue("pending")),
            "disk_usage_mb": self._get_directory_size(self.audit_dir) / (1024 * 1024),
        }

    def _get_directory_size(self, directory: Path) -> int:
        """Get directory size in bytes."""
        total_size = 0
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size

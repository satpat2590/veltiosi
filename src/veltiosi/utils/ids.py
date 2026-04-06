"""ID generation and validation utilities for Veltiosi."""

import hashlib
import time
import uuid
from datetime import datetime
from typing import Optional


def generate_uuid() -> str:
    """Generate a UUID string.

    Returns:
        UUID string
    """
    return str(uuid.uuid4())


def generate_timestamp_id(prefix: str = "") -> str:
    """Generate an ID based on timestamp.

    Args:
        prefix: Optional prefix for the ID

    Returns:
        Timestamp-based ID
    """
    timestamp = int(time.time() * 1000)  # Milliseconds
    return f"{prefix}{timestamp}"


def generate_hash_id(data: str, length: int = 8) -> str:
    """Generate a short hash ID from data.

    Args:
        data: Data to hash
        length: Length of hash to return (max 32)

    Returns:
        Short hash ID
    """
    if length > 32:
        length = 32

    # Create SHA256 hash
    hash_obj = hashlib.sha256(data.encode())
    hash_hex = hash_obj.hexdigest()

    # Return first N characters
    return hash_hex[:length]


def generate_note_id(note_title: str, note_path: str) -> str:
    """Generate a consistent ID for a note.

    Args:
        note_title: Note title
        note_path: Note path

    Returns:
        Note ID
    """
    # Combine title and path for uniqueness
    combined = f"{note_title}|{note_path}"
    return generate_hash_id(combined, length=12)


def generate_task_id(task_data: dict) -> str:
    """Generate an ID for a task.

    Args:
        task_data: Task data dictionary

    Returns:
        Task ID
    """
    # Use task ID if available, otherwise generate from title and timestamp
    if "id" in task_data:
        return f"task-{task_data['id']}"

    title = task_data.get("title", "")
    timestamp = task_data.get("created_at", datetime.now().isoformat())
    combined = f"{title}|{timestamp}"
    return f"task-{generate_hash_id(combined, length=8)}"


def generate_review_queue_id(task_id: int, timestamp: Optional[datetime] = None) -> str:
    """Generate an ID for a review queue item.

    Args:
        task_id: Task ID
        timestamp: Optional timestamp (default: now)

    Returns:
        Review queue ID
    """
    if timestamp is None:
        timestamp = datetime.now()

    # Format: YYYYMMDD-HHMMSS-task-{task_id}
    timestamp_str = timestamp.strftime("%Y%m%d-%H%M%S")
    return f"{timestamp_str}-task-{task_id}"


def parse_review_queue_id(queue_id: str) -> Optional[dict]:
    """Parse a review queue ID into its components.

    Args:
        queue_id: Review queue ID

    Returns:
        Dict with timestamp and task_id, or None if invalid
    """
    pattern = r"(\d{8})-(\d{6})-task-(\d+)"
    match = re.match(pattern, queue_id)

    if not match:
        return None

    date_str = match.group(1)
    time_str = match.group(2)
    task_id = int(match.group(3))

    try:
        timestamp = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
        return {
            "timestamp": timestamp,
            "task_id": task_id,
        }
    except ValueError:
        return None


def is_valid_uuid(uuid_str: str) -> bool:
    """Check if a string is a valid UUID.

    Args:
        uuid_str: String to check

    Returns:
        True if valid UUID
    """
    try:
        uuid_obj = uuid.UUID(uuid_str)
        return str(uuid_obj) == uuid_str
    except ValueError:
        return False


def is_valid_timestamp_id(id_str: str) -> bool:
    """Check if a string is a valid timestamp ID.

    Args:
        id_str: String to check

    Returns:
        True if valid timestamp ID
    """
    # Check if it's all digits (possibly with prefix)
    if not id_str:
        return False

    # Remove prefix if present
    if not id_str[-1].isdigit():
        # Last character is not digit, check if rest are digits
        prefix_end = len(id_str) - 1
        while prefix_end > 0 and not id_str[prefix_end].isdigit():
            prefix_end -= 1

        if prefix_end == 0:
            return False

        numeric_part = id_str[prefix_end + 1 :]
    else:
        numeric_part = id_str

    # Check if numeric part is all digits and reasonable timestamp
    if not numeric_part.isdigit():
        return False

    # Check if it's a plausible timestamp (between 2020 and 2100 in milliseconds)
    timestamp = int(numeric_part)
    min_timestamp = 1577836800000  # 2020-01-01 in milliseconds
    max_timestamp = 4102444800000  # 2100-01-01 in milliseconds

    return min_timestamp <= timestamp <= max_timestamp


def is_valid_hash_id(id_str: str, expected_length: Optional[int] = None) -> bool:
    """Check if a string is a valid hash ID.

    Args:
        id_str: String to check
        expected_length: Optional expected length

    Returns:
        True if valid hash ID
    """
    if not id_str:
        return False

    # Check if it's hexadecimal
    if not re.match(r"^[0-9a-f]+$", id_str, re.IGNORECASE):
        return False

    # Check length if specified
    if expected_length is not None and len(id_str) != expected_length:
        return False

    # Hash IDs should be between 4 and 64 characters
    return 4 <= len(id_str) <= 64


def normalize_id(id_str: str) -> str:
    """Normalize an ID string.

    Args:
        id_str: ID string

    Returns:
        Normalized ID (lowercase, no extra whitespace)
    """
    return id_str.strip().lower()


def generate_audit_run_id() -> str:
    """Generate an ID for an audit run.

    Returns:
        Audit run ID
    """
    timestamp = datetime.now()
    timestamp_str = timestamp.strftime("%Y%m%d-%H%M%S")
    random_part = generate_uuid()[:8]
    return f"audit-{timestamp_str}-{random_part}"


# Regular expression for parsing
import re

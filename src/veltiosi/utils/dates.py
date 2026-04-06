"""Date and time utilities for Veltiosi."""

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse a date string into a datetime object.

    Supports various formats:
    - ISO format: 2026-04-05
    - ISO with time: 2026-04-05T14:30:00
    - Week format: 2026-W14
    - Relative: today, yesterday, N days ago
    """
    if not date_str:
        return None

    date_str = date_str.strip().lower()

    # Relative dates
    if date_str == "today":
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_str == "yesterday":
        return (datetime.now() - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    # N days ago
    match = re.match(r"(\d+)\s+days?\s+ago", date_str)
    if match:
        days = int(match.group(1))
        return (datetime.now() - timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    # Week format: YYYY-WW
    match = re.match(r"(\d{4})-w(\d{2})", date_str, re.IGNORECASE)
    if match:
        year = int(match.group(1))
        week = int(match.group(2))
        # First day of the week (Monday)
        return datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")

    # Try ISO format
    try:
        # Try with time
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        try:
            # Try date only
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            pass

    return None


def format_date(dt: datetime, format_str: str = "iso") -> str:
    """Format a datetime object.

    Args:
        dt: Datetime object
        format_str: Format type: 'iso', 'short', 'long', 'week', or custom strftime format

    Returns:
        Formatted date string
    """
    if format_str == "iso":
        return dt.isoformat()
    elif format_str == "short":
        return dt.strftime("%Y-%m-%d")
    elif format_str == "long":
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    elif format_str == "week":
        return dt.strftime("%Y-W%W")
    else:
        return dt.strftime(format_str)


def get_week_range(date: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Get the start and end of the week containing the given date.

    Week starts on Monday, ends on Sunday.

    Args:
        date: Date to get week for (default: current date)

    Returns:
        Tuple of (week_start, week_end)
    """
    if date is None:
        date = datetime.now()

    # Monday is 0, Sunday is 6
    week_start = date - timedelta(days=date.weekday())
    week_end = week_start + timedelta(days=6)

    # Set to start/end of day
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_end.replace(hour=23, minute=59, second=59, microsecond=999999)

    return week_start, week_end


def get_week_label(date: Optional[datetime] = None) -> str:
    """Get a label for the week in YYYY-WW format.

    Args:
        date: Date to get week label for (default: current date)

    Returns:
        Week label like "2026-W14"
    """
    if date is None:
        date = datetime.now()

    year = date.year
    week = date.isocalendar()[1]
    return f"{year}-W{week:02d}"


def parse_week_label(week_label: str) -> Optional[datetime]:
    """Parse a week label (YYYY-WW) into a datetime (Monday of that week).

    Args:
        week_label: Week label like "2026-W14"

    Returns:
        Datetime for Monday of that week, or None if invalid
    """
    match = re.match(r"(\d{4})-w(\d{2})", week_label, re.IGNORECASE)
    if not match:
        return None

    year = int(match.group(1))
    week = int(match.group(2))

    try:
        # First day of the week (Monday)
        return datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")
    except ValueError:
        return None


def days_ago(days: int) -> datetime:
    """Get a datetime N days ago from now.

    Args:
        days: Number of days ago

    Returns:
        Datetime N days ago
    """
    return datetime.now() - timedelta(days=days)


def is_recent(dt: datetime, days: int = 7) -> bool:
    """Check if a datetime is within the last N days.

    Args:
        dt: Datetime to check
        days: Number of days threshold

    Returns:
        True if within last N days
    """
    return dt >= days_ago(days)


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable duration
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}h"
    else:
        days = seconds / 86400
        return f"{days:.1f}d"


def parse_date_from_filename(filename: str) -> Optional[datetime]:
    """Parse date from filename patterns.

    Supports patterns like:
    - YYYY-MM-DD.md
    - YYYY-MM-DD-title.md
    - YYYYMMDD.md
    """
    # Try YYYY-MM-DD pattern
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if match:
        try:
            year, month, day = map(int, match.groups())
            return datetime(year, month, day)
        except ValueError:
            pass

    # Try YYYYMMDD pattern
    match = re.match(r"(\d{4})(\d{2})(\d{2})", filename)
    if match:
        try:
            year, month, day = map(int, match.groups())
            return datetime(year, month, day)
        except ValueError:
            pass

    return None


def parse_date_from_content(content: str) -> Optional[datetime]:
    """Parse date from content frontmatter or text."""
    import re

    # Try to find date in frontmatter
    frontmatter_match = re.search(
        r"^---\s*\n.*?date:\s*(.+?)\s*\n.*?---", content, re.DOTALL | re.MULTILINE
    )
    if frontmatter_match:
        date_str = frontmatter_match.group(1).strip()
        parsed = parse_date(date_str)
        if parsed:
            return parsed

    # Try to find date in content (common patterns)
    date_patterns = [
        r"\b(\d{4}-\d{2}-\d{2})\b",  # YYYY-MM-DD
        r"\b(\d{2}/\d{2}/\d{4})\b",  # MM/DD/YYYY
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",  # 5 April 2026
    ]

    for pattern in date_patterns:
        match = re.search(pattern, content)
        if match:
            date_str = match.group(1)
            parsed = parse_date(date_str)
            if parsed:
                return parsed

    return None

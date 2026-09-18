"""Data models for Veltiosi."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


class RootCategory(str, Enum):
    """Canonical root categories."""

    PHYSICAL = "physical"
    MENTAL = "mental"
    FINANCIAL = "financial"
    SOCIAL = "social"
    HISTORY = "history"
    NATURE = "nature"


class NoteType(str, Enum):
    """Note types."""

    CONCEPT = "concept"
    SOURCE_SUMMARY = "source_summary"
    COMPOUNDING_PAGE = "compounding_page"
    SYNTHESIS = "synthesis"
    MOC = "moc"
    TASK_LINKED = "task_linked"
    REFERENCE = "reference"
    GENERATED_INDEX = "generated_index"


class GeneratedStatus(str, Enum):
    """Generated status of a note."""

    MANUAL = "manual"
    GENERATED = "generated"
    MIXED = "mixed"


class NoteRecord(BaseModel):
    """Record for a note in the vault."""

    # Core identifiers
    path: Path
    title: str
    domain_folder: str

    # Classification
    note_type: NoteType
    primary_root_category: Optional[RootCategory] = None
    secondary_root_categories: List[RootCategory] = Field(default_factory=list)
    subcategories: List[str] = Field(default_factory=list)

    # Content analysis
    wikilinks_out: List[str] = Field(default_factory=list)
    wikilinks_in: List[str] = Field(default_factory=list)
    has_slope_section: bool = False
    generated_status: GeneratedStatus = GeneratedStatus.MANUAL

    # Metadata
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    file_size: int = 0
    line_count: int = 0

    class Config:
        arbitrary_types_allowed = True


class TaskMappingResult(TypedDict):
    """Result of task mapping."""

    task_id: int
    confidence: float
    category: Optional[str]
    subcategories: List[str]
    tags: List[str]
    target_page: Optional[str]
    decision: str  # "auto_apply", "review_queue", "skip"


class ReviewQueueItem(BaseModel):
    """Review queue item for ambiguous task mappings."""

    queue_id: str
    status: str  # pending, approved, denied, modified, resolved
    task_id: int
    task_title: str
    ambiguity_reason: str
    proposed_mappings: List[Dict[str, Any]]
    candidate_pages: List[str]
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None


class SourceRecord(BaseModel):
    """Record for a raw source."""

    source_id: str
    title: str
    source_type: str  # article, paper, book, podcast, video, data, receipt
    source_date: Optional[datetime] = None
    source_location: str  # URL or file path
    ingested_at: datetime = Field(default_factory=datetime.now)
    summary_note_path: Optional[Path] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    """Audit event for tracking operations."""

    run_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    command: str
    mode: str  # dry-run, live
    status: str  # success, partial, failure
    notes_read: int = 0
    notes_written: int = 0
    review_items_created: int = 0
    tasks_processed: List[int] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    duration_seconds: Optional[float] = None


class LintIssue(BaseModel):
    """Lint issue."""

    issue_type: str
    note_path: Path
    severity: str  # error, warning, info
    message: str
    suggestion: Optional[str] = None
    fixable: bool = False


class QueryResult(BaseModel):
    """Query result with citations."""

    answer: str
    citations: List[str]  # wiki links
    confidence: float
    coverage_gaps: List[str]
    suggested_new_notes: List[str]

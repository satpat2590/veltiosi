"""Tests for Veltiosi data models."""

from datetime import datetime
from pathlib import Path

import pytest

from veltiosi.models import (
    AuditEvent,
    GeneratedStatus,
    LintIssue,
    NoteRecord,
    NoteType,
    QueryResult,
    ReviewQueueItem,
    RootCategory,
    SourceRecord,
)


class TestNoteRecord:
    def test_minimal_construction(self):
        note = NoteRecord(
            path=Path("01-Foo/bar.md"),
            title="Bar",
            domain_folder="01-Foo",
            note_type=NoteType.CONCEPT,
        )
        assert note.title == "Bar"
        assert note.note_type == NoteType.CONCEPT
        assert note.primary_root_category is None
        assert note.subcategories == []
        assert note.wikilinks_out == []
        assert note.wikilinks_in == []
        assert note.has_slope_section is False
        assert note.generated_status == GeneratedStatus.MANUAL

    def test_full_construction(self):
        note = NoteRecord(
            path=Path("02-Eco/gdp.md"),
            title="GDP",
            domain_folder="02-Eco",
            note_type=NoteType.COMPOUNDING_PAGE,
            primary_root_category=RootCategory.FINANCIAL,
            secondary_root_categories=[RootCategory.MENTAL],
            subcategories=["trading_systems"],
            wikilinks_out=["Inflation", "Markets"],
            wikilinks_in=["Economy"],
            has_slope_section=True,
            generated_status=GeneratedStatus.MIXED,
            created_at=datetime(2026, 1, 1),
            modified_at=datetime(2026, 3, 1),
            file_size=1024,
            line_count=50,
        )
        assert note.primary_root_category == RootCategory.FINANCIAL
        assert "trading_systems" in note.subcategories
        assert note.has_slope_section is True
        assert note.file_size == 1024

    def test_note_type_enum_values(self):
        assert NoteType.CONCEPT.value == "concept"
        assert NoteType.SOURCE_SUMMARY.value == "source_summary"
        assert NoteType.SYNTHESIS.value == "synthesis"
        assert NoteType.MOC.value == "moc"

    def test_root_category_enum_values(self):
        assert RootCategory.PHYSICAL.value == "physical"
        assert RootCategory.MENTAL.value == "mental"
        assert RootCategory.FINANCIAL.value == "financial"
        assert RootCategory.SOCIAL.value == "social"

    def test_generated_status_enum_values(self):
        assert GeneratedStatus.MANUAL.value == "manual"
        assert GeneratedStatus.GENERATED.value == "generated"
        assert GeneratedStatus.MIXED.value == "mixed"


class TestQueryResult:
    def test_construction(self):
        result = QueryResult(
            answer="The answer is 42.",
            citations=["[[Note A]]", "[[Note B]]"],
            confidence=0.85,
            coverage_gaps=["Missing info about X"],
            suggested_new_notes=["New Note"],
        )
        assert result.answer == "The answer is 42."
        assert len(result.citations) == 2
        assert result.confidence == 0.85

    def test_empty_lists_default(self):
        result = QueryResult(
            answer="Some answer",
            citations=[],
            confidence=0.5,
            coverage_gaps=[],
            suggested_new_notes=[],
        )
        assert result.citations == []
        assert result.coverage_gaps == []


class TestSourceRecord:
    def test_construction(self):
        record = SourceRecord(
            source_id="abc123",
            title="Test Source",
            source_type="article",
            source_location="https://example.com",
        )
        assert record.source_id == "abc123"
        assert record.summary_note_path is None
        assert isinstance(record.ingested_at, datetime)

    def test_with_path(self, tmp_path):
        note_path = tmp_path / "summary.md"
        record = SourceRecord(
            source_id="x1",
            title="Local File",
            source_type="paper",
            source_location="/tmp/paper.pdf",
            summary_note_path=note_path,
        )
        assert record.summary_note_path == note_path


class TestAuditEvent:
    def test_construction_defaults(self):
        event = AuditEvent(run_id="abc", command="wiki_index", mode="dry-run", status="running")
        assert event.notes_read == 0
        assert event.notes_written == 0
        assert event.warnings == []
        assert event.errors == []
        assert isinstance(event.timestamp, datetime)


class TestLintIssue:
    def test_construction(self):
        issue = LintIssue(
            issue_type="missing_slope",
            note_path=Path("foo/bar.md"),
            severity="warning",
            message="Missing slope section",
            suggestion="Add ## Slope",
            fixable=True,
        )
        assert issue.fixable is True
        assert issue.severity == "warning"

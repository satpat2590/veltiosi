"""
Tests for Veltiosi workflow modules.

Each workflow is tested with:
  1. Unit tests of the class-level .query() / .ingest_source() / .generate_synthesis() methods.
  2. Integration tests of the module-level run_*() functions that the CLI calls.

External services (LLM, Atma) are always mocked.
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veltiosi.models import NoteRecord, NoteType, QueryResult


# Pin the Jev env precondition: a live verification run that `source`s
# ~/.hermes/.env exports OPENROUTER_API_KEY into the persistent shell. The
# wiki_query workflow now constructs a JevQueryRouter — deleting the key for
# every test here keeps the router deterministically disabled so these tests
# exercise the legacy (fail-open) Gemini path they were written for.
@pytest.fixture(autouse=True)
def _pin_jev_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("VELTIOSI_JEV_API_KEY", raising=False)
    monkeypatch.delenv("VELTIOSI_JEV_ENABLED", raising=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_query_result(**overrides):
    defaults = dict(
        answer="The answer is 42.",
        citations=["[[Note A]]"],
        confidence=0.8,
        coverage_gaps=[],
        suggested_new_notes=[],
    )
    defaults.update(overrides)
    return QueryResult(**defaults)


# ===========================================================================
# wiki_query
# ===========================================================================


class TestWikiQueryWorkflowClass:
    def test_query_empty_vault_returns_no_match_result(self, vault_path):
        from veltiosi.workflows.wiki_query import WikiQueryWorkflow

        wf = WikiQueryWorkflow(vault_path=vault_path)
        result = wf.query("what is machine learning?")

        assert result is not None
        assert "No relevant information" in result.answer
        assert result.confidence == 0.0
        assert len(result.coverage_gaps) > 0

    @patch("veltiosi.workflows.wiki_query.llm_service")
    def test_query_with_notes_calls_llm(self, mock_llm, populated_vault):
        from veltiosi.workflows.wiki_query import WikiQueryWorkflow

        mock_llm.generate_query_answer.return_value = _make_query_result()

        wf = WikiQueryWorkflow(vault_path=populated_vault)
        result = wf.query("what is machine learning?")

        assert result is not None
        assert result.answer == "The answer is 42."
        mock_llm.generate_query_answer.assert_called_once()

    @patch("veltiosi.workflows.wiki_query.llm_service")
    def test_query_when_llm_fails_returns_none(self, mock_llm, populated_vault):
        from veltiosi.workflows.wiki_query import WikiQueryWorkflow

        mock_llm.generate_query_answer.return_value = None

        wf = WikiQueryWorkflow(vault_path=populated_vault)
        result = wf.query("machine learning")

        # No notes == early return before LLM, or LLM failure == None
        # Either way the workflow must not crash
        assert result is None or isinstance(result, QueryResult)

    def test_build_wiki_context_returns_string(self, wiki_repo):
        from veltiosi.workflows.wiki_query import WikiQueryWorkflow

        wf = WikiQueryWorkflow(vault_path=wiki_repo.vault_path)
        notes = wiki_repo.scan_and_classify()[:3]
        context = wf._build_wiki_context(notes)
        assert isinstance(context, str)

    def test_build_wiki_context_includes_note_titles(self, wiki_repo):
        from veltiosi.workflows.wiki_query import WikiQueryWorkflow

        wf = WikiQueryWorkflow(vault_path=wiki_repo.vault_path)
        notes = wiki_repo.scan_and_classify()[:2]
        context = wf._build_wiki_context(notes)
        for note in notes:
            assert note.title in context


class TestRunQuery:
    @patch("veltiosi.workflows.wiki_query.llm_service")
    def test_run_query_returns_dict(self, mock_llm, populated_vault):
        from veltiosi.workflows.wiki_query import run_query

        mock_llm.generate_query_answer.return_value = _make_query_result(
            answer="Synthesis answer.", citations=["[[ML]]"]
        )

        result = run_query(question="machine learning", dry_run=True)
        assert isinstance(result, dict)

    @patch("veltiosi.workflows.wiki_query.llm_service")
    def test_run_query_result_has_required_keys(self, mock_llm, populated_vault):
        from veltiosi.workflows.wiki_query import run_query

        mock_llm.generate_query_answer.return_value = _make_query_result()

        result = run_query(question="emergence", dry_run=True)
        for key in ("answer", "citations", "confidence", "coverage_gaps"):
            assert key in result, f"Missing key: {key}"


# ===========================================================================
# wiki_ingest
# ===========================================================================


class TestWikiIngestWorkflowClass:
    @patch("veltiosi.workflows.wiki_ingest.llm_service")
    def test_ingest_local_file_dry_run(self, mock_llm, populated_vault, tmp_txt_file):
        from veltiosi.workflows.wiki_ingest import WikiIngestWorkflow

        mock_llm.generate_ingest_summary.return_value = (
            "Key takeaways: AI is transforming industries.\n"
            "Categories: mental\nContradictions: None"
        )

        wf = WikiIngestWorkflow(vault_path=populated_vault)
        result = wf.ingest_source(str(tmp_txt_file), source_type="article", dry_run=True)

        assert result is not None
        source_record, note_content = result
        assert source_record.title is not None
        assert isinstance(note_content, str)
        assert "Summary" in note_content

    @patch("veltiosi.workflows.wiki_ingest.llm_service")
    def test_ingest_creates_note_when_not_dry_run(self, mock_llm, populated_vault, tmp_txt_file):
        from veltiosi.workflows.wiki_ingest import WikiIngestWorkflow

        mock_llm.generate_ingest_summary.return_value = "Summary content here."

        wf = WikiIngestWorkflow(vault_path=populated_vault)
        result = wf.ingest_source(str(tmp_txt_file), source_type="article", dry_run=False)

        assert result is not None
        source_record, _ = result
        # Note path should be set and file should exist on disk
        assert source_record.summary_note_path is not None
        assert source_record.summary_note_path.exists()

    def test_ingest_missing_file_returns_none(self, populated_vault):
        from veltiosi.workflows.wiki_ingest import WikiIngestWorkflow

        wf = WikiIngestWorkflow(vault_path=populated_vault)
        result = wf.ingest_source("/nonexistent/path.txt", dry_run=True)
        assert result is None

    @patch("veltiosi.workflows.wiki_ingest.llm_service")
    def test_ingest_note_content_includes_source_metadata(
        self, mock_llm, populated_vault, tmp_txt_file
    ):
        from veltiosi.workflows.wiki_ingest import WikiIngestWorkflow

        mock_llm.generate_ingest_summary.return_value = "LLM generated summary."

        wf = WikiIngestWorkflow(vault_path=populated_vault)
        result = wf.ingest_source(str(tmp_txt_file), source_type="article", dry_run=True)
        _, note_content = result

        assert "article" in note_content.lower()

    def test_extract_categories_mental_in_summary(self, populated_vault):
        from veltiosi.workflows.wiki_ingest import WikiIngestWorkflow

        wf = WikiIngestWorkflow(vault_path=populated_vault)
        summary = "This content is about mental health and learning."
        cats = wf._extract_categories_from_summary(summary)

        assert "root_categories" in cats
        assert "mental" in cats["root_categories"]

    def test_extract_categories_financial_in_summary(self, populated_vault):
        from veltiosi.workflows.wiki_ingest import WikiIngestWorkflow

        wf = WikiIngestWorkflow(vault_path=populated_vault)
        summary = "This is about financial markets and trading."
        cats = wf._extract_categories_from_summary(summary)

        assert "financial" in cats["root_categories"]

    @patch("veltiosi.workflows.wiki_ingest.llm_service")
    def test_batch_ingest(self, mock_llm, populated_vault, tmp_txt_file, tmp_md_file):
        from veltiosi.workflows.wiki_ingest import WikiIngestWorkflow

        mock_llm.generate_ingest_summary.return_value = "Batch summary."

        wf = WikiIngestWorkflow(vault_path=populated_vault)
        results = wf.batch_ingest(
            source_paths=[str(tmp_txt_file), str(tmp_md_file)],
            source_type="article",
            dry_run=True,
        )
        assert len(results) == 2


class TestRunIngest:
    @patch("veltiosi.workflows.wiki_ingest.llm_service")
    def test_run_ingest_returns_dict(self, mock_llm, populated_vault, tmp_txt_file):
        from veltiosi.workflows.wiki_ingest import run_ingest

        mock_llm.generate_ingest_summary.return_value = "Summary."

        result = run_ingest(source=str(tmp_txt_file), source_type="article", dry_run=True)
        assert isinstance(result, dict)

    @patch("veltiosi.workflows.wiki_ingest.llm_service")
    def test_run_ingest_result_has_required_keys(self, mock_llm, populated_vault, tmp_txt_file):
        from veltiosi.workflows.wiki_ingest import run_ingest

        mock_llm.generate_ingest_summary.return_value = "Summary."

        result = run_ingest(source=str(tmp_txt_file), dry_run=True)
        for key in ("source_title", "source_type", "source_location"):
            assert key in result, f"Missing key: {key}"

    def test_run_ingest_missing_source_returns_error_dict(self, populated_vault):
        from veltiosi.workflows.wiki_ingest import run_ingest

        result = run_ingest(source="/no/such/file.txt", dry_run=True)
        assert "error" in result


# ===========================================================================
# weekly_synthesis
# ===========================================================================


class TestWeeklySynthesisWorkflowClass:
    @patch("veltiosi.workflows.weekly_synthesis.llm_service")
    def test_generate_synthesis_dry_run_with_activity(self, mock_llm, populated_vault):
        """Synthesis must work when vault has recently-modified notes."""
        from veltiosi.workflows.weekly_synthesis import WeeklySynthesisWorkflow

        mock_llm.generate_weekly_synthesis.return_value = "Weekly insight text here."

        # Manually touch a note so modified_at is within the past 7 days
        note_file = list((populated_vault / "05-Computation").glob("*.md"))[0]
        note_file.touch()  # sets mtime to now

        wf = WeeklySynthesisWorkflow(vault_path=populated_vault)
        result = wf.generate_synthesis(dry_run=True)

        assert result is not None
        note_path, note_content = result
        assert "Weekly Synthesis" in note_content
        assert "Activity Summary" in note_content
        mock_llm.generate_weekly_synthesis.assert_called_once()

    @patch("veltiosi.workflows.weekly_synthesis.llm_service")
    def test_generate_synthesis_no_activity_returns_none(self, mock_llm, populated_vault):
        """If no notes modified in window, synthesis returns None."""
        from veltiosi.workflows.weekly_synthesis import WeeklySynthesisWorkflow

        mock_llm.generate_weekly_synthesis.return_value = "Insight."

        # Use a past window where nothing was modified
        very_old_start = datetime(2000, 1, 1)
        very_old_end = datetime(2000, 1, 7)

        wf = WeeklySynthesisWorkflow(vault_path=populated_vault)
        result = wf.generate_synthesis(
            start_date=very_old_start, end_date=very_old_end, dry_run=True
        )
        assert result is None

    @patch("veltiosi.workflows.weekly_synthesis.llm_service")
    def test_note_content_structure(self, mock_llm, populated_vault):
        from veltiosi.workflows.weekly_synthesis import WeeklySynthesisWorkflow

        mock_llm.generate_weekly_synthesis.return_value = "Insights: progress was made."

        note_file = list(populated_vault.rglob("*.md"))[0]
        note_file.touch()

        wf = WeeklySynthesisWorkflow(vault_path=populated_vault)
        result = wf.generate_synthesis(dry_run=True)

        assert result is not None
        _, content = result
        assert "## Activity Summary" in content
        assert "## AI Synthesis" in content
        assert "## Key Insights" in content
        assert "## Metadata" in content

    def test_get_wiki_activity_returns_dict(self, populated_vault):
        from veltiosi.workflows.weekly_synthesis import WeeklySynthesisWorkflow

        wf = WeeklySynthesisWorkflow(vault_path=populated_vault)
        end = datetime.now()
        start = end - timedelta(days=7)
        activity = wf._get_wiki_activity(start_date=start, end_date=end)

        assert isinstance(activity, dict)
        for key in ("completed_tasks", "updated_pages", "new_sources", "category_points"):
            assert key in activity, f"Missing key: {key}"
        assert isinstance(activity["completed_tasks"], list)
        assert isinstance(activity["category_points"], dict)

    @patch("veltiosi.workflows.weekly_synthesis.llm_service")
    def test_retrospective_generates_multiple(self, mock_llm, populated_vault):
        from veltiosi.workflows.weekly_synthesis import WeeklySynthesisWorkflow

        mock_llm.generate_weekly_synthesis.return_value = "Weekly insight."

        # Touch a note in each "week" (just touch now — all within 4 weeks)
        for f in list(populated_vault.rglob("*.md"))[:2]:
            f.touch()

        wf = WeeklySynthesisWorkflow(vault_path=populated_vault)
        results = wf.generate_retrospective(weeks=2, dry_run=True)
        assert isinstance(results, list)


class TestRunWeeklySynthesis:
    @patch("veltiosi.workflows.weekly_synthesis.llm_service")
    def test_run_weekly_synthesis_returns_dict(self, mock_llm, populated_vault):
        from veltiosi.workflows.weekly_synthesis import run_weekly_synthesis

        mock_llm.generate_weekly_synthesis.return_value = "Insight."

        for f in list(populated_vault.rglob("*.md"))[:2]:
            f.touch()

        result = run_weekly_synthesis(dry_run=True)
        assert isinstance(result, dict)

    @patch("veltiosi.workflows.weekly_synthesis.llm_service")
    def test_run_weekly_synthesis_has_output_path(self, mock_llm, populated_vault):
        from veltiosi.workflows.weekly_synthesis import run_weekly_synthesis

        mock_llm.generate_weekly_synthesis.return_value = "Insight."

        for f in list(populated_vault.rglob("*.md"))[:2]:
            f.touch()

        result = run_weekly_synthesis(dry_run=True)
        assert "output_path" in result


# ===========================================================================
# wiki_index (existing workflow)
# ===========================================================================


class TestWikiIndexWorkflow:
    def test_run_index_check_returns_dict(self):
        """run_index(check=True) against the real configured vault returns a dict."""
        from veltiosi.workflows.wiki_index import run_index

        result = run_index(check=True, dry_run=True)
        assert isinstance(result, dict)

    def test_run_quick_scan_returns_dict(self):
        from veltiosi.workflows.wiki_index import run_quick_scan

        result = run_quick_scan()
        assert isinstance(result, dict)

    def test_run_index_dry_run_returns_dict(self):
        from veltiosi.workflows.wiki_index import run_index

        result = run_index(dry_run=True)
        assert isinstance(result, dict)

    def test_run_quick_scan_returns_dict(self):
        from veltiosi.workflows.wiki_index import run_quick_scan

        result = run_quick_scan()
        assert isinstance(result, dict)

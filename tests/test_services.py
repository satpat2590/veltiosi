"""
Tests for Veltiosi service layer.

Covers:
  - WikiRepository: scan, read, write, search, alias methods
  - RetrievalService: retrieve_for_query, retrieve_for_source
  - SourceLoader: local files, title extraction
  - LLMService: MockProvider, service routing, all generation helpers
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veltiosi.models import NoteRecord, NoteType, QueryResult, RootCategory
from veltiosi.services.llm_service import LLMService, MockProvider
from veltiosi.services.retrieval import RetrievalService
from veltiosi.services.source_loader import SourceLoader
from veltiosi.services.wiki_repository import WikiRepository


# ===========================================================================
# WikiRepository
# ===========================================================================


class TestWikiRepositoryInit:
    def test_init_with_vault_path(self, populated_vault):
        repo = WikiRepository(vault_path=populated_vault)
        assert repo.vault_path == populated_vault

    def test_vault_path_stored(self, populated_vault):
        repo = WikiRepository(vault_path=populated_vault)
        assert repo.vault_path.exists()


class TestWikiRepositoryScan:
    def test_scan_empty_vault_returns_list(self, vault_path):
        repo = WikiRepository(vault_path=vault_path)
        notes = repo.scan_and_classify()
        assert isinstance(notes, list)
        assert len(notes) == 0

    def test_scan_populated_vault_returns_notes(self, wiki_repo):
        notes = wiki_repo.scan_and_classify()
        assert len(notes) > 0
        for note in notes:
            assert isinstance(note, NoteRecord)

    def test_scan_all_notes_alias(self, wiki_repo):
        """scan_all_notes() must be an alias for scan_and_classify()."""
        via_classify = wiki_repo.scan_and_classify()
        wiki_repo._notes_cache = None  # force rescan
        via_alias = wiki_repo.scan_all_notes()
        assert len(via_alias) == len(via_classify)

    def test_scan_caches_result(self, wiki_repo):
        notes1 = wiki_repo.scan_and_classify()
        notes2 = wiki_repo.scan_and_classify()
        assert notes1 is notes2  # same object from cache

    def test_force_rescan_refreshes_cache(self, wiki_repo):
        notes1 = wiki_repo.scan_and_classify()
        notes2 = wiki_repo.scan_and_classify(force_rescan=True)
        # Different objects but same length
        assert len(notes1) == len(notes2)
        assert notes1 is not notes2

    def test_notes_have_required_fields(self, wiki_repo):
        notes = wiki_repo.scan_and_classify()
        for note in notes:
            assert note.title, f"Note at {note.path} has no title"
            assert note.domain_folder, f"Note at {note.path} has no domain_folder"
            assert note.note_type is not None


class TestWikiRepositoryReadWrite:
    def test_write_and_read_relative_path(self, empty_wiki_repo):
        content = "# Hello\n\nTest content."
        empty_wiki_repo.write_note("test/hello.md", content)
        result = empty_wiki_repo.read_note_content("test/hello.md")
        assert result == content

    def test_write_and_read_absolute_path(self, empty_wiki_repo):
        note_path = empty_wiki_repo.vault_path / "subdir" / "note.md"
        content = "# Absolute\n\nWritten via absolute path."
        empty_wiki_repo.write_note(note_path, content)
        result = empty_wiki_repo.read_note_content(note_path)
        assert result == content

    def test_write_creates_parent_dirs(self, empty_wiki_repo):
        deep_path = "a/b/c/deep.md"
        empty_wiki_repo.write_note(deep_path, "# Deep")
        assert (empty_wiki_repo.vault_path / deep_path).exists()

    def test_read_nonexistent_returns_none(self, empty_wiki_repo):
        result = empty_wiki_repo.read_note_content("nonexistent.md")
        assert result is None

    def test_write_invalidates_cache(self, wiki_repo):
        wiki_repo.scan_and_classify()
        assert wiki_repo._notes_cache is not None
        wiki_repo.write_note("new_note.md", "# New")
        assert wiki_repo._notes_cache is None


class TestWikiRepositorySearch:
    def test_search_finds_matching_notes(self, wiki_repo):
        # SAMPLE_NOTES includes "Machine Learning" — search should find it
        results = wiki_repo.search_notes_by_content("machine learning")
        assert len(results) > 0
        titles = [n.title.lower() for n in results]
        assert any("machine learning" in t or "deep learning" in t for t in titles)

    def test_search_case_insensitive(self, wiki_repo):
        lower = wiki_repo.search_notes_by_content("emergence")
        upper = wiki_repo.search_notes_by_content("EMERGENCE")
        assert len(lower) == len(upper)

    def test_search_no_match_returns_empty(self, wiki_repo):
        results = wiki_repo.search_notes_by_content("xyzzy_not_a_real_term_12345")
        assert results == []

    def test_search_returns_list_of_note_records(self, wiki_repo):
        results = wiki_repo.search_notes_by_content("neural")
        for r in results:
            assert isinstance(r, NoteRecord)


class TestWikiRepositoryLookup:
    def test_get_notes_by_type(self, wiki_repo):
        notes = wiki_repo.scan_and_classify()
        for note in notes:
            by_type = wiki_repo.get_notes_by_type(note.note_type)
            assert note in by_type

    def test_get_notes_by_domain(self, wiki_repo):
        notes = wiki_repo.scan_and_classify()
        if notes:
            first = notes[0]
            by_domain = wiki_repo.get_notes_by_domain(first.domain_folder)
            assert first in by_domain


# ===========================================================================
# RetrievalService
# ===========================================================================


class TestRetrievalServiceQuery:
    def test_retrieve_returns_list(self, retrieval_service):
        results = retrieval_service.retrieve_for_query("machine learning")
        assert isinstance(results, list)

    def test_retrieve_relevant_to_topic(self, retrieval_service):
        results = retrieval_service.retrieve_for_query("neural networks machine learning")
        assert len(results) > 0
        titles = [n.title.lower() for n in results]
        assert any(
            "machine" in t or "learning" in t or "deep" in t or "neural" in t for t in titles
        )

    def test_retrieve_respects_max_notes(self, retrieval_service):
        results = retrieval_service.retrieve_for_query("learning", max_notes=2)
        assert len(results) <= 2

    def test_retrieve_returns_note_records(self, retrieval_service):
        results = retrieval_service.retrieve_for_query("systems")
        for r in results:
            assert isinstance(r, NoteRecord)

    def test_retrieve_empty_vault_returns_empty(self, empty_wiki_repo):
        svc = RetrievalService(repository=empty_wiki_repo)
        results = svc.retrieve_for_query("anything")
        assert results == []


class TestRetrievalServiceSource:
    def test_retrieve_for_source_returns_list(self, retrieval_service):
        results = retrieval_service.retrieve_for_source(
            source_title="AI Research Paper",
            source_content="This paper discusses machine learning and neural networks.",
        )
        assert isinstance(results, list)

    def test_retrieve_for_source_respects_max_notes(self, retrieval_service):
        results = retrieval_service.retrieve_for_source(
            source_title="Anything",
            source_content="emergence systems thinking",
            max_notes=1,
        )
        assert len(results) <= 1


class TestRetrievalServiceCitations:
    def test_format_citations(self, retrieval_service, wiki_repo):
        notes = wiki_repo.scan_and_classify()[:2]
        citations = retrieval_service.format_citations(notes)
        assert len(citations) == len(notes)
        for c in citations:
            assert "[[" in c

    def test_deduplicate_citations(self, retrieval_service):
        dupes = ["[[A]]", "[[B]]", "[[A]]", "[[C]]", "[[B]]"]
        deduped = retrieval_service.deduplicate_citations(dupes)
        assert deduped == ["[[A]]", "[[B]]", "[[C]]"]
        assert len(deduped) == 3


# ===========================================================================
# SourceLoader
# ===========================================================================


class TestSourceLoaderLocalFile:
    def test_load_txt_file_returns_content_and_title(self, source_loader, tmp_txt_file):
        content, title = source_loader.load_source(str(tmp_txt_file))
        assert content is not None
        assert isinstance(content, str)
        assert "machine learning" in content.lower()
        assert title is not None
        assert isinstance(title, str)

    def test_load_md_file_extracts_h1_title(self, source_loader, tmp_md_file):
        content, title = source_loader.load_source(str(tmp_md_file))
        assert title == "Markdown Note"

    def test_load_missing_file_returns_none_none(self, source_loader):
        content, title = source_loader.load_source("/nonexistent/path/file.txt")
        assert content is None
        assert title is None

    def test_load_returns_strings_not_records(self, source_loader, tmp_txt_file):
        """Critical: load_source must return (str, str), not (SourceRecord, str)."""
        content, title = source_loader.load_source(str(tmp_txt_file))
        assert isinstance(content, str), f"Expected str, got {type(content)}"
        assert isinstance(title, str), f"Expected str, got {type(title)}"

    def test_content_is_sliceable(self, source_loader, tmp_txt_file):
        """Regression: SourceRecord was returned instead of str, causing TypeError on slice."""
        content, _ = source_loader.load_source(str(tmp_txt_file))
        # This should not raise TypeError
        snippet = content[:100]
        assert isinstance(snippet, str)


class TestSourceLoaderTitleExtraction:
    def test_extract_title_from_h1(self, source_loader):
        content = "# My Title\n\nSome body text."
        title = source_loader._extract_title_from_content(content, fallback="fallback")
        assert title == "My Title"

    def test_extract_title_from_h2_if_no_h1(self, source_loader):
        content = "## Secondary Heading\n\nBody."
        title = source_loader._extract_title_from_content(content, fallback="fallback")
        assert title == "Secondary Heading"

    def test_extract_title_fallback_when_no_heading(self, source_loader):
        content = "Just some plain text without any heading."
        title = source_loader._extract_title_from_content(content, fallback="my_fallback")
        # Fallback is title-cased from filename stem
        assert "My Fallback" in title or "fallback" in title.lower()

    def test_sanitize_filename(self, source_loader):
        name = source_loader.sanitize_filename("Hello: World? <Test>")
        assert "<" not in name
        assert ">" not in name
        assert ":" not in name
        assert "?" not in name

    def test_sanitize_filename_length_limit(self, source_loader):
        long_name = "a" * 200
        result = source_loader.sanitize_filename(long_name, max_length=50)
        assert len(result) <= 50

    def test_infer_type_from_path(self, source_loader, tmp_path):
        assert source_loader._infer_source_type_from_path(Path("foo.md")) == "article"
        assert source_loader._infer_source_type_from_path(Path("foo.pdf")) == "paper"
        assert source_loader._infer_source_type_from_path(Path("foo.csv")) == "data"
        assert source_loader._infer_source_type_from_path(Path("foo.txt")) == "article"


class TestSourceLoaderURL:
    """URL loading tests use a mocked requests.get so no network needed."""

    def _make_mock_response(self, html: str):
        m = MagicMock()
        m.status_code = 200
        m.content = html.encode("utf-8")
        m.raise_for_status = MagicMock()
        return m

    def test_load_url_returns_content_and_title(self, source_loader):
        html = "<html><head><title>Test Page</title></head><body><article><p>Content about AI.</p></article></body></html>"
        with patch("requests.get", return_value=self._make_mock_response(html)):
            content, title = source_loader.load_source("https://example.com/article")
        assert title == "Test Page"
        assert content is not None
        assert isinstance(content, str)

    def test_load_url_returns_strings_not_records(self, source_loader):
        html = "<html><head><title>T</title></head><body><p>Body text here for the test.</p></body></html>"
        with patch("requests.get", return_value=self._make_mock_response(html)):
            content, title = source_loader.load_source("https://example.com/test")
        assert isinstance(content, str), f"Expected str, got {type(content)}"

    def test_load_url_network_error_returns_none(self, source_loader):
        import requests as req

        with patch("requests.get", side_effect=req.exceptions.ConnectionError("no network")):
            content, title = source_loader.load_source("https://example.com/test")
        assert content is None
        assert title is None


# ===========================================================================
# LLMService / MockProvider
# ===========================================================================


class TestMockProvider:
    def test_test_connection_returns_true(self, mock_llm_provider):
        assert mock_llm_provider.test_connection() is True

    def test_generate_returns_string(self, mock_llm_provider):
        result = mock_llm_provider.generate_content("tell me something")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_with_task_type(self, mock_llm_provider):
        for task_type in ("ingest", "query", "synthesis", "classification", "default"):
            result = mock_llm_provider.generate_content("prompt", task_type=task_type)
            assert result is not None, f"No result for task_type={task_type}"

    def test_generate_with_context(self, mock_llm_provider):
        result = mock_llm_provider.generate_content("prompt", context="some context")
        assert result is not None
        assert isinstance(result, str)


class TestLLMServiceWithMockProvider:
    def test_generate_content_returns_string(self, llm_service_mock_only):
        result = llm_service_mock_only.generate_content("test prompt")
        assert isinstance(result, str)

    def test_generate_ingest_summary(self, llm_service_mock_only):
        result = llm_service_mock_only.generate_ingest_summary(
            source_title="Article",
            source_type="article",
            source_content="Some content about AI",
            wiki_context="Existing wiki notes...",
        )
        assert result is not None
        assert isinstance(result, str)

    def test_generate_query_answer_returns_query_result(self, llm_service_mock_only):
        result = llm_service_mock_only.generate_query_answer(
            question="What is machine learning?",
            wiki_context="Machine learning is a method of teaching computers.",
        )
        assert result is not None
        assert isinstance(result, QueryResult)
        assert isinstance(result.answer, str)
        assert isinstance(result.citations, list)
        assert 0.0 <= result.confidence <= 1.0

    def test_generate_weekly_synthesis_returns_string(self, llm_service_mock_only):
        result = llm_service_mock_only.generate_weekly_synthesis(
            completed_tasks=["Task A", "Task B"],
            updated_pages=["Page X"],
            new_sources=["Source 1"],
            category_points={"mental": 5, "physical": 2},
        )
        assert result is not None
        assert isinstance(result, str)

    def test_classify_note_returns_dict(self, llm_service_mock_only):
        result = llm_service_mock_only.classify_note(
            title="Test",
            content="This is about learning and education.",
            domain_folder="learning",
        )
        assert result is not None
        assert isinstance(result, dict)
        assert "primary_root_category" in result

    def test_generate_content_falls_through_providers(self, llm_service_mock_only):
        """If first provider returns None, service should try next."""
        from veltiosi.services.llm_service import MockProvider

        failing = MockProvider()
        failing.generate_content = MagicMock(return_value=None)
        working = MockProvider()

        llm_service_mock_only.providers = [failing, working]
        result = llm_service_mock_only.generate_content("test")
        assert result is not None

    def test_test_all_connections(self, llm_service_mock_only):
        report = llm_service_mock_only.test_all_connections()
        assert isinstance(report, dict)
        for provider_name, ok in report.items():
            assert isinstance(provider_name, str)
            assert isinstance(ok, bool)

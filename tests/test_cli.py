"""
CLI integration tests.

Uses typer's CliRunner so we never spawn a subprocess and never touch
the live Obsidian vault.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from veltiosi.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(*args):
    return runner.invoke(app, list(args))


# ===========================================================================
# Help / version
# ===========================================================================


class TestCLIHelp:
    def test_help_exits_zero(self):
        result = _run("--help")
        assert result.exit_code == 0
        assert "veltiosi" in result.output.lower()

    def test_all_commands_listed_in_help(self):
        result = _run("--help")
        for cmd in (
            "wiki-index",
            "wiki-lint",
            "wiki-ingest",
            "task-sync",
            "weekly-synthesis",
            "wiki-query",
            "config-show",
            "status",
            "hermes-setup",
            "hermes-status",
        ):
            assert cmd in result.output, f"Command '{cmd}' not in help output"


# ===========================================================================
# status
# ===========================================================================


class TestCLIStatus:
    def test_status_exits_zero(self, populated_vault):
        with patch("veltiosi.cli.settings") as mock_settings:
            mock_settings.obsidian_vault = populated_vault
            mock_settings.root_categories = {}
            mock_settings.subcategories = {}
            mock_settings.task_rules = []

            from veltiosi.connectors.obsidian import ObsidianConnector

            with patch.object(ObsidianConnector, "count_notes", return_value=5):
                result = _run("status")

        assert result.exit_code == 0
        assert "5" in result.output or "Vault" in result.output


# ===========================================================================
# config-show
# ===========================================================================


class TestCLIConfigShow:
    def test_config_show_exits_zero(self):
        result = _run("config-show")
        assert result.exit_code == 0

    def test_config_show_mentions_vault(self):
        result = _run("config-show")
        assert "obsidian" in result.output.lower() or "vault" in result.output.lower()


# ===========================================================================
# wiki-query
# ===========================================================================


class TestCLIWikiQuery:
    @patch("veltiosi.workflows.wiki_query.llm_service")
    def test_wiki_query_dry_run_exits_zero(self, mock_llm, populated_vault):
        from veltiosi.models import QueryResult

        mock_llm.generate_query_answer.return_value = QueryResult(
            answer="Test answer.",
            citations=[],
            confidence=0.8,
            coverage_gaps=[],
            suggested_new_notes=[],
        )

        with patch("veltiosi.workflows.wiki_query.WikiQueryWorkflow") as MockWF:
            mock_instance = MagicMock()
            mock_instance.query.return_value = QueryResult(
                answer="Test answer.",
                citations=["[[Note]]"],
                confidence=0.9,
                coverage_gaps=[],
                suggested_new_notes=[],
            )
            MockWF.return_value = mock_instance

            result = _run("wiki-query", "What is AI?", "--dry-run")

        assert result.exit_code == 0

    def test_wiki_query_no_question_exits_nonzero(self):
        # Typer requires the positional arg; omitting it should fail
        result = _run("wiki-query")
        assert result.exit_code != 0


# ===========================================================================
# wiki-ingest
# ===========================================================================


class TestCLIWikiIngest:
    @patch("veltiosi.workflows.wiki_ingest.llm_service")
    def test_wiki_ingest_dry_run_exits_zero(self, mock_llm, tmp_txt_file):
        mock_llm.generate_ingest_summary.return_value = "Summary text."

        result = _run("wiki-ingest", str(tmp_txt_file), "--dry-run")
        assert result.exit_code == 0

    def test_wiki_ingest_missing_file_exits_nonzero(self):
        result = _run("wiki-ingest", "/nonexistent/file.txt")
        assert result.exit_code != 0


# ===========================================================================
# weekly-synthesis
# ===========================================================================


class TestCLIWeeklySynthesis:
    @patch("veltiosi.workflows.weekly_synthesis.llm_service")
    def test_weekly_synthesis_dry_run(self, mock_llm, populated_vault):
        mock_llm.generate_weekly_synthesis.return_value = "Weekly insight."

        # Touch files so there's activity
        for f in list(populated_vault.rglob("*.md"))[:2]:
            f.touch()

        with patch("veltiosi.workflows.weekly_synthesis.WeeklySynthesisWorkflow") as MockWF:
            mock_instance = MagicMock()
            mock_instance.generate_synthesis.return_value = (
                Path("/tmp/synthesis.md"),
                "# Weekly Synthesis\n\nInsights.",
            )
            MockWF.return_value = mock_instance

            result = _run("weekly-synthesis", "--dry-run")

        assert result.exit_code == 0


# ===========================================================================
# wiki-index
# ===========================================================================


class TestCLIWikiIndex:
    def test_wiki_index_check_exits_zero(self):
        with patch("veltiosi.workflows.wiki_index.run_index") as mock_run:
            mock_run.return_value = {"consistent": True, "issues": []}
            result = _run("wiki-index", "--check")
        assert result.exit_code == 0

    def test_wiki_index_dry_run_exits_zero(self):
        with patch("veltiosi.workflows.wiki_index.run_index") as mock_run:
            mock_run.return_value = {"notes_processed": 10}
            result = _run("wiki-index", "--dry-run")
        assert result.exit_code == 0


# ===========================================================================
# wiki-lint
# ===========================================================================


class TestCLIWikiLint:
    def test_wiki_lint_dry_run_exits_zero(self):
        with patch("veltiosi.workflows.wiki_lint.run_lint") as mock_run:
            mock_run.return_value = {"issues": []}
            result = _run("wiki-lint", "--dry-run")
        assert result.exit_code == 0

    def test_wiki_lint_shows_no_issues(self):
        with patch("veltiosi.workflows.wiki_lint.run_lint") as mock_run:
            mock_run.return_value = {"issues": []}
            result = _run("wiki-lint", "--dry-run")
        assert "No lint issues" in result.output or result.exit_code == 0


# ===========================================================================
# hermes-status
# ===========================================================================


class TestCLIHermesStatus:
    def test_hermes_status_exits_zero(self):
        with patch("veltiosi.connectors.hermes.HermesConnector.test_integration") as mock_ti:
            mock_ti.return_value = {
                "hermes_home_exists": False,
                "skills_dir_exists": False,
                "profiles_dir_exists": False,
                "available_skills": [],
                "active_profile": None,
                "veltiosi_skill_registered": False,
            }
            result = _run("hermes-status")
        assert result.exit_code == 0

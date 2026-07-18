"""
Shared pytest fixtures for the Veltiosi test suite.

Design principles:
- Every fixture that touches the filesystem uses a real temp directory.
- The live Obsidian vault (~/ Obsidian) is NEVER touched.
- External services (LLM, network) are always mocked.
- Fixtures are composed: vault_path -> wiki_repo -> retrieval_service etc.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the installed package is importable regardless of working directory
# ---------------------------------------------------------------------------
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_NOTES: dict[str, str] = {
    "01-Natural-Philosophy/Emergence.md": textwrap.dedent("""\
        # Emergence

        Emergence is the process by which complex systems arise from simple rules.

        ## Key Concepts
        - Self-organisation
        - Non-linearity
        - Complex adaptive systems

        ## Slope
        Understanding emergence helps explain phenomena across physics, biology and economics.

        ## Related
        - [[Systems Thinking]]
        - [[Complexity Theory]]
    """),
    "01-Natural-Philosophy/Systems Thinking.md": textwrap.dedent("""\
        # Systems Thinking

        Systems thinking is a holistic approach to analysis.

        ## Slope
        Systemic approaches consistently outperform linear models.

        ## Related
        - [[Emergence]]
    """),
    "05-Computation/Machine Learning.md": textwrap.dedent("""\
        # Machine Learning

        Machine learning is a subset of artificial intelligence.

        ## Key Concepts
        - Supervised learning
        - Neural networks
        - Gradient descent

        ## Slope
        ML capabilities are growing exponentially.
    """),
    "05-Computation/Deep Learning.md": textwrap.dedent("""\
        # Deep Learning

        Deep learning uses multi-layer neural networks.

        ## Related
        - [[Machine Learning]]
    """),
    "17-References/source_summaries/Test Article.md": textwrap.dedent("""\
        # Test Article

        A summary of a test article about python programming.

        **Source Type:** article
        **Source:** /tmp/test.txt
        **Ingested:** 2026-04-06
    """),
}


def _write_vault(vault_path: Path, notes: dict[str, str] | None = None) -> None:
    """Write note files into vault_path."""
    if notes is None:
        notes = SAMPLE_NOTES
    for rel, content in notes.items():
        dest = vault_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault_path() -> Generator[Path, None, None]:
    """An empty temporary vault directory."""
    with tempfile.TemporaryDirectory(prefix="veltiosi_test_vault_") as d:
        yield Path(d)


@pytest.fixture
def populated_vault(vault_path: Path) -> Path:
    """A temp vault pre-populated with SAMPLE_NOTES."""
    _write_vault(vault_path)
    return vault_path


@pytest.fixture
def audit_dir() -> Generator[Path, None, None]:
    """Isolated temp directory for audit logs."""
    with tempfile.TemporaryDirectory(prefix="veltiosi_audit_") as d:
        yield Path(d)


# ---------------------------------------------------------------------------
# Service fixtures  (always use populated_vault so ObsidianConnector won't blow)
# ---------------------------------------------------------------------------


@pytest.fixture
def wiki_repo(populated_vault: Path):
    """WikiRepository pointed at the populated temp vault."""
    from veltiosi.services.wiki_repository import WikiRepository

    return WikiRepository(vault_path=populated_vault)


@pytest.fixture
def empty_wiki_repo(vault_path: Path):
    """WikiRepository pointed at an EMPTY temp vault."""
    from veltiosi.services.wiki_repository import WikiRepository

    return WikiRepository(vault_path=vault_path)


@pytest.fixture
def retrieval_service(wiki_repo):
    """RetrievalService backed by the populated temp vault."""
    from veltiosi.services.retrieval import RetrievalService

    return RetrievalService(repository=wiki_repo)


@pytest.fixture
def source_loader():
    """SourceLoader (no external deps)."""
    from veltiosi.services.source_loader import SourceLoader

    return SourceLoader()


@pytest.fixture
def mock_llm_provider():
    """The built-in MockProvider that never calls any API."""
    from veltiosi.services.llm_service import MockProvider

    return MockProvider()


@pytest.fixture
def llm_service_mock_only():
    """LLMService whose provider list is replaced with only MockProvider."""
    from veltiosi.services.llm_service import LLMService, MockProvider

    svc = LLMService.__new__(LLMService)
    svc.providers = [MockProvider()]
    return svc


# ---------------------------------------------------------------------------
# Source-file fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_txt_file(tmp_path: Path) -> Path:
    """A temp .txt file with simple content."""
    f = tmp_path / "article.txt"
    f.write_text("# My Article\n\nThis is content about machine learning and AI.", encoding="utf-8")
    return f


@pytest.fixture
def tmp_md_file(tmp_path: Path) -> Path:
    """A temp .md file."""
    f = tmp_path / "note.md"
    f.write_text("# Markdown Note\n\nPython is a programming language.", encoding="utf-8")
    return f

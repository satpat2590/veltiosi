# Veltiosi — Testing Guide

The test suite has **123 tests** across five files. All tests run fully offline — no Gemini API key is required, and the live Obsidian vault is never touched.

---

## Contents

1. [Quick start](#1-quick-start)
2. [Prerequisites](#2-prerequisites)
3. [Running the tests](#3-running-the-tests)
4. [Test layout](#4-test-layout)
5. [What each file tests](#5-what-each-file-tests)
6. [How fixtures work](#6-how-fixtures-work)
7. [Mocking strategy](#7-mocking-strategy)
8. [System health check](#8-system-health-check)
9. [Coverage](#9-coverage)
10. [Adding new tests](#10-adding-new-tests)

---

## 1. Quick start

```bash
cd ~/veltiosi
pip install -e ".[dev]"   # installs pytest and pytest-cov
python -m pytest tests/   # run the full suite
```

Expected output:

```
123 passed, 2 warnings in ~1.5s
```

The two warnings are upstream deprecation notices from `google-generativeai` and `pydantic`; they do not affect behaviour.

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | Required by `pyproject.toml` |
| Package installed | Run `pip install -e .` once before testing |
| No API keys needed | All LLM calls use `MockProvider` during tests |
| No Obsidian vault needed | Tests build isolated temp vaults |

Install dev dependencies:

```bash
pip install -e ".[dev]"
```

Verify the installation is correct:

```bash
python -c "import veltiosi; print('OK')"
```

---

## 3. Running the tests

### Run everything

```bash
python -m pytest tests/
```

### Run a single file

```bash
python -m pytest tests/test_services.py
python -m pytest tests/test_workflows.py
python -m pytest tests/test_audit.py
python -m pytest tests/test_models.py
python -m pytest tests/test_cli.py
```

### Run a single test class or test

```bash
python -m pytest tests/test_services.py::TestWikiRepositoryScan
python -m pytest tests/test_services.py::TestWikiRepositoryScan::test_scan_empty_vault_returns_list
```

### Stop on the first failure

```bash
python -m pytest tests/ -x
```

### Verbose output (show each test name)

```bash
python -m pytest tests/ -v
```

### Quiet output (just pass/fail counts)

```bash
python -m pytest tests/ -q
```

### Using the helper script

```bash
./run_tests.py               # same as python -m pytest tests/
./run_tests.py --verbose     # -v flag
./run_tests.py --coverage    # adds coverage report
./run_tests.py --test tests/test_services.py
```

---

## 4. Test layout

```
tests/
├── conftest.py         # Shared fixtures: temp vaults, mocked services, sample notes
├── test_models.py      # Pydantic model construction and field validation
├── test_audit.py       # AuditLogger: run lifecycle, errors, review queue, reports
├── test_services.py    # WikiRepository, RetrievalService, SourceLoader, LLMService
├── test_workflows.py   # wiki_query, wiki_ingest, weekly_synthesis, wiki_index
└── test_cli.py         # CLI commands via typer.testing.CliRunner
```

---

## 5. What each file tests

### test_models.py (12 tests)

Verifies that every Pydantic model can be constructed, that required fields enforce correct types, and that enum values match their string representations.

| Class | What is tested |
|-------|---------------|
| `NoteRecord` | Minimal and full construction, enum field values |
| `QueryResult` | Construction with and without optional lists |
| `SourceRecord` | Default `ingested_at`, optional `summary_note_path` |
| `AuditEvent` | Default zero counts and empty lists |
| `LintIssue` | Severity, path, fixable flag |

---

### test_audit.py (17 tests)

Tests the full lifecycle of the `AuditLogger`.

| Group | What is tested |
|-------|---------------|
| Initialisation | Subdirectories are created on construction |
| Run lifecycle | `start_run` returns a string ID and creates a JSON file; `complete_run` sets status; `update_run` sets `notes_read`; `log_error` and `log_warning` append correctly; multiple errors accumulate |
| Review queue | `add_to_review_queue` returns a non-None ID and creates a file; `get_review_queue` returns pending items; `update_review_item` moves status to resolved |
| Stats | `get_stats` returns a dict; event counts match what was written |
| Reports | `generate_report` returns a dict with `summary`, `events`, `review_queue_stats`; run counts are accurate |

---

### test_services.py (47 tests)

The largest file. Uses a pre-populated temp vault (`populated_vault` fixture) for every test.

**WikiRepository (20 tests)**

| Group | What is tested |
|-------|---------------|
| Init | `vault_path` is stored; vault directory exists |
| Scan | Empty vault returns `[]`; populated vault returns `NoteRecord` objects; `scan_all_notes()` is a working alias; results are cached; `force_rescan=True` returns a fresh list; every note has a title and domain folder |
| Read/Write | Relative path round-trip; absolute path round-trip; parent directories are created; missing file returns `None`; writing invalidates the cache |
| Search | Finds notes containing a keyword; case-insensitive; no-match returns `[]`; results are `NoteRecord` objects |
| Lookup | `get_notes_by_type` and `get_notes_by_domain` return subsets of the vault |

**RetrievalService (7 tests)**

| What is tested |
|---------------|
| Returns a list for any query |
| Results contain notes relevant to the topic |
| `max_notes` is respected |
| Results are `NoteRecord` objects |
| Empty vault returns `[]` |
| `retrieve_for_source` returns a list and respects `max_notes` |
| `format_citations` produces `[[Title]]` strings; `deduplicate_citations` removes duplicates |

**SourceLoader (12 tests)**

| What is tested |
|---------------|
| `.txt` file: returns `(str, str)` — critical regression test for the bug where `SourceRecord` was returned instead of `str` |
| `.md` file: title is extracted from the `# Heading` |
| Missing file: returns `(None, None)` |
| Content is sliceable (guards against the `TypeError` regression) |
| `_extract_title_from_content` with `# H1`, `## H2`, and no heading (fallback) |
| `sanitize_filename` strips illegal characters and respects `max_length` |
| `_infer_source_type_from_path` maps extensions correctly |
| URL loading (mocked): returns `(str, str)`; network error returns `(None, None)` |

**LLMService / MockProvider (8 tests)**

| What is tested |
|---------------|
| `MockProvider.test_connection()` returns `True` |
| `generate_content` returns a non-empty string for all task types |
| Context is accepted without error |
| `LLMService.generate_content` returns a string |
| `generate_ingest_summary` returns a string |
| `generate_query_answer` returns a `QueryResult` with correct types |
| `generate_weekly_synthesis` returns a string |
| `classify_note` returns a dict with `primary_root_category` |
| Provider fallback: if first provider returns `None`, the next is tried |
| `test_all_connections` returns `{str: bool}` |

---

### test_workflows.py (37 tests)

Tests both the class-level methods and the `run_*` functions used by the CLI.

**wiki_query (7 tests)**

| What is tested |
|---------------|
| Empty vault: returns a graceful "no information" result with `confidence=0.0` |
| Populated vault: `retrieve_for_query` finds notes, then `llm_service.generate_query_answer` is called once |
| LLM failure: workflow returns `None` without crashing |
| `_build_wiki_context` returns a string containing note titles |
| `run_query` returns a dict |
| Result dict has `answer`, `citations`, `confidence`, `coverage_gaps` keys |

**wiki_ingest (10 tests)**

| What is tested |
|---------------|
| Dry run with a local file: returns `(SourceRecord, str)` |
| Live run: note file is created on disk |
| Missing file: returns `None` |
| Note content contains source metadata |
| Category extraction: `mental` detected from "mental health" |
| Category extraction: `financial` detected from "financial markets" |
| Batch ingest: processes two files and returns two results |
| `run_ingest` returns a dict |
| Dict has `source_title`, `source_type`, `source_location` keys |
| Missing source returns `{"error": ...}` dict |

**weekly_synthesis (9 tests)**

| What is tested |
|---------------|
| With recent activity: synthesis is generated; LLM is called once |
| Old date window with no activity: returns `None` |
| Note content contains `Activity Summary`, `AI Synthesis`, `Key Insights`, `Metadata` |
| `_get_wiki_activity` returns a dict with all four required keys |
| `generate_retrospective` returns a list |
| `run_weekly_synthesis` returns a dict |
| Dict contains `output_path` key |

**wiki_index (3 tests)**

| What is tested |
|---------------|
| `run_index(check=True, dry_run=True)` returns a dict |
| `run_quick_scan()` returns a dict |
| `run_index(dry_run=True)` returns a dict |

---

### test_cli.py (14 tests)

Uses `typer.testing.CliRunner` — no subprocess, no real vault.

| Command | What is tested |
|---------|---------------|
| `--help` | Exits 0; output contains all 10 command names |
| `status` | Exits 0 with mocked vault |
| `config-show` | Exits 0; output mentions "vault" or "obsidian" |
| `wiki-query "?"` | Exits 0 with mocked workflow; exits non-zero when no question given |
| `wiki-ingest <file>` | Exits 0 with a valid file; exits non-zero with a missing file |
| `weekly-synthesis` | Exits 0 with mocked workflow |
| `wiki-index` | `--check` and `--dry-run` both exit 0 with mocked `run_index` |
| `wiki-lint` | `--dry-run` exits 0; "No lint issues" shown when result is empty |
| `hermes-status` | Exits 0 with mocked `test_integration` |

---

## 6. How fixtures work

All fixtures are defined in `tests/conftest.py`.

### Vault fixtures

```
vault_path          Empty temp directory. Deleted after each test.
populated_vault     Same, but pre-written with 5 sample markdown notes:
                    ├── 01-Natural-Philosophy/Emergence.md
                    ├── 01-Natural-Philosophy/Systems Thinking.md
                    ├── 05-Computation/Machine Learning.md
                    ├── 05-Computation/Deep Learning.md
                    └── 17-References/source_summaries/Test Article.md
```

### Service fixtures

```
wiki_repo           WikiRepository(vault_path=populated_vault)
empty_wiki_repo     WikiRepository(vault_path=vault_path)
retrieval_service   RetrievalService(repository=wiki_repo)
source_loader       SourceLoader()
mock_llm_provider   MockProvider()
llm_service_mock_only   LLMService with providers=[MockProvider()]
```

### File fixtures

```
tmp_txt_file    tmp_path/article.txt  — content about machine learning
tmp_md_file     tmp_path/note.md      — content about Python
audit_dir       Isolated temp dir for AuditLogger
```

---

## 7. Mocking strategy

**LLM calls** are mocked at the `llm_service` module attribute using `unittest.mock.patch`:

```python
@patch("veltiosi.workflows.wiki_query.llm_service")
def test_query_calls_llm(mock_llm, populated_vault):
    mock_llm.generate_query_answer.return_value = QueryResult(
        answer="The answer.", citations=["[[Note A]]"],
        confidence=0.8, coverage_gaps=[], suggested_new_notes=[],
    )
    wf = WikiQueryWorkflow(vault_path=populated_vault)
    result = wf.query("question")
    mock_llm.generate_query_answer.assert_called_once()
```

**HTTP calls** are mocked using `patch("requests.get")`:

```python
def test_load_url(source_loader):
    mock_resp = MagicMock()
    mock_resp.content = b"<html><title>T</title><body><p>Body.</p></body></html>"
    mock_resp.raise_for_status = MagicMock()
    with patch("requests.get", return_value=mock_resp):
        content, title = source_loader.load_source("https://example.com")
    assert title == "T"
```

**Filesystem** uses real temp directories. Nothing in the test suite touches `~/Obsidian`.

---

## 8. System health check

`check_system.py` is a separate end-to-end script that calls the real CLI via subprocess against the configured vault. Run it to verify the whole system works together:

```bash
./check_system.py
```

It runs eight checks:

1. `veltiosi status`
2. `veltiosi config-show`
3. `veltiosi wiki-index --check`
4. `veltiosi wiki-lint --dry-run`
5. `veltiosi wiki-query 'test query' --dry-run`
6. `veltiosi wiki-ingest /tmp/test_source.txt --dry-run`
7. `veltiosi weekly-synthesis --dry-run`
8. `veltiosi hermes-status`

A passing run ends with:

```
SUMMARY: 8/8 tests passed
✓ All tests passed! Veltiosi is ready to use.
```

> **Note:** `check_system.py` requires `VELTIOSI_OBSIDIAN_VAULT` to point to a real directory. The pytest suite does not.

---

## 9. Coverage

```bash
python -m pytest tests/ --cov=veltiosi --cov-report=term-missing
```

Or via the helper:

```bash
./run_tests.py --coverage
```

To generate an HTML report:

```bash
python -m pytest tests/ --cov=veltiosi --cov-report=html
open htmlcov/index.html
```

---

## 10. Adding new tests

### Checklist

- [ ] Place the test in the most specific file (`test_services.py` for a service class, `test_workflows.py` for a workflow, etc.)
- [ ] Use fixtures from `conftest.py` rather than creating temp directories by hand
- [ ] Mock any LLM call using `@patch("veltiosi.workflows.<module>.llm_service")`
- [ ] Mock any HTTP call using `@patch("requests.get")`
- [ ] Never reference `~/Obsidian` or any path outside `tmp_path` / `populated_vault`
- [ ] Name the test after what it asserts, not what it calls (`test_search_finds_matching_notes` not `test_search`)

### Example: adding a service test

```python
# tests/test_services.py

class TestWikiRepositoryMyNewFeature:
    def test_new_method_returns_correct_type(self, wiki_repo):
        result = wiki_repo.some_new_method("argument")
        assert isinstance(result, list)
```

### Example: adding a workflow test with mocked LLM

```python
# tests/test_workflows.py

@patch("veltiosi.workflows.wiki_ingest.llm_service")
def test_ingest_sets_correct_source_type(mock_llm, populated_vault, tmp_txt_file):
    from veltiosi.workflows.wiki_ingest import WikiIngestWorkflow

    mock_llm.generate_ingest_summary.return_value = "Summary."

    wf = WikiIngestWorkflow(vault_path=populated_vault)
    result = wf.ingest_source(str(tmp_txt_file), source_type="paper", dry_run=True)

    assert result is not None
    source_record, _ = result
    assert source_record.source_type == "paper"
```

# Veltiosi — Project Documentation

Veltiosi is a Python automation layer that sits on top of an Obsidian markdown vault. It indexes notes, classifies them into a four-root taxonomy, ingests external sources, syncs completed tasks, queries the knowledge base with citations, and generates weekly synthesis notes — all from a CLI, with every mutating operation supporting `--dry-run`.

---

## Contents

1. [What it does](#1-what-it-does)
2. [Repository layout](#2-repository-layout)
3. [Configuration](#3-configuration)
4. [CLI commands](#4-cli-commands)
5. [Service layer](#5-service-layer)
6. [Workflow modules](#6-workflow-modules)
7. [Data models](#7-data-models)
8. [Connectors](#8-connectors)
9. [Audit system](#9-audit-system)
10. [Hermes integration](#10-hermes-integration)
11. [Dependencies](#11-dependencies)

---

## 1. What it does

| Feature | Description |
|---------|-------------|
| **Index** | Scans the vault, classifies every note by type and root category, builds backlink graphs, and writes Map-of-Content files. |
| **Lint** | Detects orphans, weak links, stale pages, missing slope sections, and missing category assignments. |
| **Ingest** | Loads a local file or URL, retrieves related existing notes, sends everything to the LLM, and writes a structured summary note into the vault. |
| **Query** | Given a plain-English question, retrieves the most relevant notes, builds context, calls the LLM, and returns an answer with `[[wikilink]]` citations. |
| **Synthesis** | Reads vault activity for a date window, tallies it by root category, and generates a weekly insight note via LLM. |
| **Task sync** | Fetches completed tasks from Atma, maps them to vault pages using rule-based matching, and either auto-applies or queues ambiguous ones for manual review. |
| **LLM fallback** | Gemini is tried first. If the API key is absent the system falls back to a mock provider so every workflow still runs. |

---

## 2. Repository layout

```
veltiosi/
├── config/                        # YAML configuration files
│   ├── categories.yaml            # Four root categories and note-type definitions
│   ├── subcategories.yaml         # Subcategories with domain-folder mappings
│   ├── domain_map.yaml            # Vault folder → root category mappings
│   ├── task_rules.yaml            # Rule-based task-to-wiki matching
│   ├── generation_rules.yaml      # Safety rules, markers, ignored paths
│   └── llm.yaml                   # LLM provider, model policy, prompts
│
├── src/veltiosi/
│   ├── cli.py                     # Typer CLI (10 commands)
│   ├── settings.py                # Pydantic settings loader
│   ├── models.py                  # Shared data models
│   ├── audit.py                   # Audit logger and review queue
│   │
│   ├── connectors/
│   │   ├── obsidian.py            # Vault read / write / scan
│   │   ├── atma.py                # Atma task API client
│   │   ├── gemini.py              # Google Gemini connector
│   │   └── hermes.py              # Hermes agent integration
│   │
│   ├── indexing/
│   │   ├── scanner.py             # Vault file discovery
│   │   ├── classifier.py          # Category / subcategory classifier
│   │   ├── backlinks.py           # Backlink graph (NetworkX)
│   │   └── index_builder.py       # MOC and local-index writer
│   │
│   ├── services/                  # Shared service layer
│   │   ├── wiki_repository.py     # Unified vault access (scan, read, write, search)
│   │   ├── retrieval.py           # Note ranking and retrieval
│   │   ├── source_loader.py       # File and URL content loading
│   │   └── llm_service.py         # LLM abstraction with provider fallback
│   │
│   ├── workflows/
│   │   ├── wiki_index.py          # Index and MOC generation
│   │   ├── wiki_lint.py           # Health and consistency checks
│   │   ├── wiki_ingest.py         # Source ingestion pipeline
│   │   ├── wiki_query.py          # Natural-language query pipeline
│   │   ├── weekly_synthesis.py    # Weekly synthesis generation
│   │   └── task_sync.py           # Atma task synchronisation
│   │
│   └── utils/
│       ├── dates.py               # Date parsing helpers
│       ├── ids.py                 # Hash and UUID generation
│       ├── markdown.py            # Heading, wikilink, marker utilities
│       └── text.py                # Keyword extraction, similarity
│
├── tests/
│   ├── conftest.py                # Shared fixtures and sample vault
│   ├── test_models.py             # Data model tests
│   ├── test_audit.py              # Audit logger tests
│   ├── test_services.py           # Service layer tests
│   ├── test_workflows.py          # Workflow module tests
│   └── test_cli.py                # CLI integration tests
│
├── .env                           # Local environment variables (not committed)
├── pyproject.toml                 # Package metadata and tool config
├── run_tests.py                   # Test runner helper script
├── check_system.py                # End-to-end system health check
├── DOCS.md                        # This file
└── TESTING.md                     # Testing guide
```

---

## 3. Configuration

All configuration lives in `config/`. Settings are loaded once at import time and exposed via `veltiosi.settings.settings`.

### Environment variables

Create a `.env` file in the project root:

```
VELTIOSI_OBSIDIAN_VAULT=/home/satyamini/Obsidian
GOOGLE_API_KEY=your_gemini_key_here

# Optional
VELTIOSI_AUDIT_DIR=/path/to/audit
ATMA_BASE_URL=http://localhost:8000
ATMA_API_KEY=your_atma_key_here
HERMES_HOME=/home/satyamini/.hermes
```

### YAML files

| File | Purpose |
|------|---------|
| `categories.yaml` | Defines the four root categories (Physical, Mental, Financial, Social) and all eight note types |
| `subcategories.yaml` | Ten subcategories (Health, Exercise, Nutrition, Relationships, Language Learning, Poetry, Research, Trading Systems, Data Engineering, Computation) each mapped to domain folders |
| `domain_map.yaml` | Maps numbered vault folders (e.g. `01-Natural-Philosophy`) to their default root categories |
| `task_rules.yaml` | Eight rules that match task titles via keyword lists to categories and wiki pages |
| `generation_rules.yaml` | Generated-section markers, review-queue settings, logging behaviour, ignored paths, lint thresholds |
| `llm.yaml` | Provider (`google`), per-task model mapping, generation parameters, and all LLM prompt templates |

### Generated-section markers

Veltiosi wraps machine-generated content in HTML comment markers so manual prose is never overwritten:

```
<!-- veltiosi:generated:start -->
... generated content ...
<!-- veltiosi:generated:end -->
```

---

## 4. CLI commands

Run `veltiosi --help` at any time. All mutating commands accept `--dry-run`.

```
veltiosi status                      Show vault note count and system health
veltiosi config-show                 Print loaded configuration

veltiosi wiki-index                  Scan vault, classify notes, write MOC files
veltiosi wiki-index --check          Check consistency without writing
veltiosi wiki-index --dry-run        Show what would change

veltiosi wiki-lint                   Detect orphans, weak links, missing slope sections
veltiosi wiki-lint --fix-safe        Apply safe fixes automatically
veltiosi wiki-lint --dry-run         Preview fixes without writing

veltiosi wiki-ingest <source>        Ingest a local file or URL
veltiosi wiki-ingest <source> --type article|paper|book|podcast|video|data|receipt
veltiosi wiki-ingest <source> --dry-run

veltiosi wiki-query "<question>"     Answer a question with wiki citations
veltiosi wiki-query "<question>" --save-note   Write the answer as a vault note

veltiosi weekly-synthesis            Generate a weekly insight note
veltiosi weekly-synthesis --week 2026-14
veltiosi weekly-synthesis --dry-run

veltiosi task-sync                   Sync completed Atma tasks (last 7 days)
veltiosi task-sync --days 30
veltiosi task-sync --task-id 123
veltiosi task-sync --dry-run

veltiosi hermes-status               Show Hermes integration state
veltiosi hermes-setup                Register Veltiosi as a Hermes skill
```

---

## 5. Service layer

The four service classes in `src/veltiosi/services/` are the foundation every workflow builds on.

### WikiRepository

Unified interface to the vault. Wraps `ObsidianConnector`, `VaultScanner`, `NoteClassifier`, and `BacklinkAnalyzer`.

| Method | What it does |
|--------|-------------|
| `scan_and_classify()` | Full vault scan with classification and backlink analysis. Results are cached until a write occurs. |
| `scan_all_notes()` | Alias for `scan_and_classify()`. |
| `search_notes_by_content(query)` | Case-insensitive substring search across titles and file content. |
| `read_note_content(path)` | Reads a note by relative or absolute path. |
| `write_note(path, content)` | Writes a note, creating parent directories as needed. Invalidates the cache. |
| `get_notes_by_category(category)` | Filter by `RootCategory` enum. |
| `get_notes_by_type(note_type)` | Filter by `NoteType` enum. |
| `get_related_notes(note)` | Notes linked to or from the given note. |
| `get_vault_statistics()` | Counts by type, category, domain folder. |

### RetrievalService

Scores and ranks notes against a query or source.

| Method | What it does |
|--------|-------------|
| `retrieve_for_query(query, max_notes, min_similarity)` | Retrieves the most relevant notes for a user question. Scoring combines title similarity, keyword overlap, category match, and backlink popularity. |
| `retrieve_for_source(source_title, source_content, source_type, max_notes)` | Retrieves existing notes most relevant to a new source being ingested. |
| `retrieve_for_weekly_synthesis(start, end)` | Groups recently-modified notes by root category for the synthesis workflow. |
| `format_citations(notes)` | Formats notes as `[[Title]] (domain_folder)` strings. |
| `deduplicate_citations(citations)` | Removes duplicates while preserving order. |

### SourceLoader

Loads content from local files and URLs.

| Method | What it does |
|--------|-------------|
| `load_source(location, source_type)` | Returns `(content: str, title: str)`. Works for `.txt`, `.md`, `.pdf`, `.csv`, `.json` and any HTTP/HTTPS URL. |
| `_extract_title_from_content(content, fallback)` | Finds the first `# Heading` or `## Heading`, falls back to the filename stem. |
| `sanitize_filename(title, max_length)` | Strips invalid characters for safe filesystem use. |
| `generate_summary_note_path(source_record)` | Derives a vault path from source type and title. |

### LLMService

Provider-agnostic LLM interface with ordered fallback.

| Method | What it does |
|--------|-------------|
| `generate_content(prompt, context, task_type)` | Tries each provider in order until one returns a result. |
| `generate_ingest_summary(...)` | Renders the `ingest` prompt template and calls the LLM. |
| `generate_query_answer(question, wiki_context)` | Renders the `query` prompt, returns a `QueryResult`. |
| `generate_weekly_synthesis(...)` | Renders the `synthesis` prompt. |
| `classify_note(title, content, domain_folder)` | Returns a classification dict (`primary_root_category`, `subcategories`, `note_type`). |
| `test_all_connections()` | Returns `{ProviderName: bool}` for each configured provider. |

**Provider order:** `GeminiProvider` (if `GOOGLE_API_KEY` is set) → `MockProvider` (always present as last resort).

---

## 6. Workflow modules

Each workflow has a class with the core logic and a `run_*` function that adds audit logging and returns a plain dict for the CLI.

### wiki_index

- Scans the vault and classifies every note.
- Builds backlink graphs.
- Writes root-category MOC files (`14-Maps-of-Content/`).
- Writes local domain-index files in each numbered folder.
- `run_index(full, check, dry_run)` → dict with counts and any inconsistencies.

### wiki_lint

- Detects **orphan notes** (no incoming links).
- Detects **stale notes** (not modified in N days).
- Detects **missing slope sections** on notes that require one.
- Detects **missing category assignments**.
- Detects **index drift** (MOC out of sync with vault).
- With `--fix-safe` applies low-risk fixes (adds stub slope sections, updates generated MOC entries).
- `run_lint(report, fix_safe, dry_run)` → dict with a list of `LintIssue` objects.

### wiki_ingest

- Loads a local file or URL via `SourceLoader`.
- Retrieves related existing notes via `RetrievalService`.
- Calls the LLM for a structured summary (key takeaways, categories, contradictions, suggested links).
- Writes the summary note into the vault.
- `run_ingest(source, source_type, domain, dry_run)` → dict with `source_title`, `summary_note_path`.

### wiki_query

- Retrieves the most relevant notes for the question.
- If no relevant notes are found, returns a graceful "no information" result.
- Otherwise builds a context window and calls the LLM.
- Returns a `QueryResult` with `answer`, `citations`, `confidence`, `coverage_gaps`.
- `run_query(question, category, save_note, dry_run)` → dict.

### weekly_synthesis

- Scans the vault for notes modified within the given date window.
- Categorises activity into completed tasks, updated pages, and new sources.
- Tallies category points.
- Calls the LLM with the activity summary.
- Writes a structured synthesis note to `synthesis/weekly/`.
- `run_weekly_synthesis(week, dry_run)` → dict with `output_path`.

### task_sync

- Fetches completed tasks from Atma for the given number of days.
- Applies rule-based matching (confidence scoring).
- High-confidence matches are auto-applied to compounding pages.
- Low-confidence matches are written to the review queue as markdown notes.
- `run_task_sync(days, task_id, dry_run)` → dict with counts.

---

## 7. Data models

All models are Pydantic v2 classes defined in `src/veltiosi/models.py`.

| Model | Key fields |
|-------|-----------|
| `NoteRecord` | `path`, `title`, `domain_folder`, `note_type`, `primary_root_category`, `subcategories`, `wikilinks_out`, `wikilinks_in`, `has_slope_section`, `generated_status`, `modified_at` |
| `QueryResult` | `answer`, `citations`, `confidence`, `coverage_gaps`, `suggested_new_notes` |
| `SourceRecord` | `source_id`, `title`, `source_type`, `source_location`, `ingested_at`, `summary_note_path` |
| `AuditEvent` | `run_id`, `command`, `mode`, `status`, `notes_read`, `notes_written`, `warnings`, `errors`, `duration_seconds` |
| `ReviewQueueItem` | `queue_id`, `task_id`, `task_title`, `ambiguity_reason`, `proposed_mappings`, `status` |
| `LintIssue` | `issue_type`, `note_path`, `severity`, `message`, `suggestion`, `fixable` |

**Enums:** `RootCategory` (physical, mental, financial, social) · `NoteType` (concept, source_summary, compounding_page, synthesis, moc, task_linked, reference, generated_index) · `GeneratedStatus` (manual, generated, mixed)

---

## 8. Connectors

| Connector | Purpose |
|-----------|---------|
| `ObsidianConnector` | Direct vault I/O: scan, read, write, append, update generated sections, calculate backlinks. |
| `AtmaConnector` | HTTP client for the Atma task API. Fetches recent completions, batch-maps tasks, marks tasks as processed. Requires `ATMA_BASE_URL` and `ATMA_API_KEY`. |
| `GeminiConnector` | Low-level Google Gemini wrapper with safety settings and per-task model routing. Used internally by `GeminiProvider` in the LLM service. |
| `HermesConnector` | Reads and writes to the Hermes agent installation at `~/.hermes`. Registers Veltiosi as a skill, creates profiles, and sets up cron job scripts. |

---

## 9. Audit system

`AuditLogger` (`src/veltiosi/audit.py`) writes structured JSON to `~/.veltiosi/audit/` (or `VELTIOSI_AUDIT_DIR`).

**Directory structure:**

```
audit/
├── events/          # One JSON file per run (named by run_id)
├── review_queue/    # Pending task-mapping items awaiting human review
└── reports/         # Generated summary reports
```

**Run lifecycle:**

```python
audit = AuditLogger()
run_id = audit.start_run("wiki_index", mode="live")   # creates event file
audit.update_run(run_id, status="running", notes_read=93)
audit.log_warning(run_id, "Stale note detected")
audit.complete_run(run_id, status="success", duration_seconds=4.2)
```

**Review queue:** Ambiguous task mappings are added via `add_to_review_queue()` and resolved via `update_review_item()`. The queue is readable through `get_review_queue(status="pending")`.

---

## 10. Hermes integration

Veltiosi registers itself as a Hermes skill so it can be invoked through the Hermes agent interface.

**Check current state:**
```
veltiosi hermes-status
```

**Register / configure:**
```
veltiosi hermes-setup
```

**Use through Hermes:**
```
hermes veltiosi status
hermes veltiosi wiki-query "What have I learned about machine learning?"
hermes veltiosi wiki-ingest ~/Downloads/paper.pdf --type paper
hermes veltiosi weekly-synthesis
```

The `hermes-setup` command writes a skill file to `~/.hermes/skills/veltiosi.py`, creates a profile config at `~/.hermes/profiles/satya/config.json`, and generates a cron setup script.

---

## 11. Dependencies

| Package | Purpose |
|---------|---------|
| `typer` | CLI framework |
| `pydantic` | Data models and settings validation |
| `pyyaml` | YAML configuration loading |
| `jinja2` | Prompt and template rendering |
| `requests` | HTTP source loading |
| `beautifulsoup4` | HTML content extraction |
| `google-generativeai` | Gemini API client |
| `networkx` | Backlink graph analysis |
| `python-dateutil` | Date parsing |
| `rich` | Terminal formatting |

**Dev only:** `pytest`, `pytest-cov`, `ruff`, `black`, `mypy`

Install:
```bash
pip install -e .          # runtime only
pip install -e ".[dev]"   # includes test and lint tools
```

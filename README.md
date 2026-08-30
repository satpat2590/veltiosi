# Veltiosi

Automation layer for the Obsidian knowledge base, implementing Karpathy's LLM Wiki pattern with a sustainable, compounding wiki system.

## Purpose

Veltiosi maintains a sustainable, compounding wiki in `~/Obsidian` by:

- **Indexing & Classification**: Scanning vault, classifying notes into canonical roots (Physical, Mental, Financial, Social)
- **Lint & Governance**: Detecting orphans, weak links, stale pages, missing slope sections
- **Source Ingestion**: Processing raw sources (articles, papers, books) into summarized notes
- **Task Synchronization**: Syncing Atma task completions to compounding pages with review queue for ambiguous mappings
- **Weekly Synthesis**: Generating periodic synthesis notes with category balance analysis
- **Query Layer**: Answering questions with citations from the wiki
- **Hermes Integration**: Operating through Hermes Agent / Satya interface

## Architecture

- **Knowledge store**: `~/Obsidian` (markdown vault with 20+ domain folders)
- **Automation logic**: `~/veltiosi` (this Python package)
- **Task source**: Atma task management system
- **Agent interface**: Hermes Agent / Satya (operating interface)
- **Primary LLM**: Google Gemini (automation model family)
- **Canonical roots**: Physical, Mental, Financial, Social (dual-index strategy)
- **Audit system**: JSON audit logs with run tracking and review queue

## Current Status (2026-04-06)

✅ **MVP Complete**: All core workflows implemented with modular architecture  
✅ **Milestone A**: Bootstrap & Configuration - Complete  
✅ **Milestone B**: Core Utilities & Connectors - Complete  
✅ **Milestone C**: Indexing & Classification - Complete  
✅ **Milestone D**: Workflow Modules & LLM Integration - Complete  

**Implemented Features**:
- **Core Infrastructure**: Vault scanning, note classification, backlink analysis
- **Shared Services**: Wiki repository, retrieval, source loading, LLM service with fallback
- **Workflow Modules**: 
  - `wiki_query`: Natural language querying with citations
  - `wiki_ingest`: Source processing with LLM summarization
  - `weekly_synthesis`: Activity analysis and insight generation
  - `task_sync`: Task completion synchronization (updated)
  - `wiki_index`: Index generation (existing)
  - `wiki_lint`: Lint and governance (existing)
- **LLM Integration**: Google Gemini as primary, configurable fallback, mock provider for testing
- **Testing**: Comprehensive test suite with pytest fixtures
- **Configuration**: Modular YAML configs with environment variable support

## Installation

```bash
cd ~/veltiosi
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

1. **Environment variables**: Copy `.env.example` to `.env`:
```bash
VELTIOSI_OBSIDIAN_VAULT=/home/satyamini/Obsidian
GOOGLE_API_KEY=your_gemini_api_key_here
ATMA_BASE_URL=http://localhost:8000  # Optional
ATMA_API_KEY=your_atma_api_key_here  # Optional
```

2. **Taxonomy configuration**: Edit YAML files in `config/`:
- `categories.yaml`: Root categories (Physical, Mental, Financial, Social)
- `subcategories.yaml`: Subcategories like Health, Trading Systems, etc.
- `domain_map.yaml`: Domain folder to root category mapping
- `task_rules.yaml`: Task mapping rules for Atma completions
- `generation_rules.yaml`: Safety and generation rules
- `llm.yaml`: Google Gemini configuration

## Usage

### Core Commands

```bash
# Indexing & Classification
veltiosi wiki-index                    # Generate/update all indexes
veltiosi wiki-index --check            # Check consistency without writing
veltiosi wiki-index --dry-run          # Show what would be done

# Lint & Governance
veltiosi wiki-lint                     # Lint for health and consistency

# Source Processing
veltiosi wiki-ingest <source> [--type article|paper|book|podcast|video|data|receipt]
veltiosi wiki-ingest article.txt --type article --dry-run  # Preview without writing

# Task Synchronization
veltiosi task-sync --days 7            # Sync Atma task completions
veltiosi task-sync --task-id 123       # Sync specific task

# Weekly Synthesis
veltiosi weekly-synthesis              # Generate weekly synthesis
veltiosi weekly-synthesis --weeks 4 --retrospective  # Generate multiple weeks

# Wiki Querying
veltiosi wiki-query "question"         # Query wiki with citations
veltiosi wiki-query --interactive      # Interactive query mode

# System Information
veltiosi status                        # Show system status
veltiosi config-show                   # Show current configuration
```

### Example Workflows

**Basic Maintenance:**
```bash
# 1. Check vault health
veltiosi status
veltiosi wiki-lint

# 2. Update indexes
veltiosi wiki-index --dry-run
veltiosi wiki-index

# 3. Sync recent tasks
veltiosi task-sync --days 7 --dry-run
veltiosi task-sync --days 7
```

**Knowledge Processing:**
```bash
# 1. Ingest a source
veltiosi wiki-ingest article.pdf --type article
veltiosi wiki-ingest https://example.com/article --type article --dry-run

# 2. Query your knowledge
veltiosi wiki-query "What have I learned about machine learning?"
veltiosi wiki-query --interactive

# 3. Generate weekly insights
veltiosi weekly-synthesis
veltiosi weekly-synthesis --weeks 4 --retrospective
```

**Development & Testing:**
```bash
# Run test suite
./run_tests.py
./run_tests.py --coverage
./run_tests.py --test tests/test_services.py --verbose

# Test LLM integration (without API key)
python -c "from src.veltiosi.services.llm_service import MockProvider; p = MockProvider(); print(p.generate_content('test'))"
```

## Project Structure

```
veltiosi/
├── config/                    # Configuration files
│   ├── categories.yaml       # Root categories
│   ├── subcategories.yaml    # Subcategories
│   ├── domain_map.yaml       # Domain folder mapping
│   ├── task_rules.yaml       # Task mapping rules
│   ├── generation_rules.yaml # Safety rules
│   └── llm.yaml             # LLM configuration
├── src/veltiosi/
│   ├── __init__.py          # Package metadata
│   ├── settings.py          # Settings loader
│   ├── models.py            # Data models
│   ├── cli.py              # CLI interface
│   ├── audit.py            # Audit logging
│   ├── connectors/         # External service connectors
│   │   ├── obsidian.py    # Obsidian vault
│   │   ├── atma.py        # Atma tasks
│   │   ├── gemini.py      # Google Gemini
│   │   └── hermes.py      # Hermes integration
│   ├── services/          # Shared services
│   │   ├── wiki_repository.py  # Vault access abstraction
│   │   ├── retrieval.py        # Note retrieval and ranking
│   │   ├── source_loader.py    # Source loading and parsing
│   │   └── llm_service.py      # LLM with fallback support
│   ├── indexing/          # Indexing & classification
│   │   ├── scanner.py    # Vault scanner
│   │   ├── classifier.py # Note classifier
│   │   ├── backlinks.py  # Backlink analysis
│   │   └── index_builder.py # Index builder
│   ├── workflows/        # Workflow orchestration
│   │   ├── wiki_index.py # Indexing workflow
│   │   ├── wiki_lint.py  # Lint and governance
│   │   ├── wiki_ingest.py # Source ingestion
│   │   ├── wiki_query.py  # Natural language querying
│   │   ├── weekly_synthesis.py # Weekly insights
│   │   └── task_sync.py  # Task synchronization
│   └── utils/           # Utility modules
│       ├── dates.py     # Date utilities
│       ├── markdown.py  # Markdown utilities
│       ├── text.py      # Text processing
│       └── ids.py       # ID generation
├── tests/              # Test suite
│   ├── conftest.py     # Pytest fixtures
│   ├── test_services.py # Service layer tests
│   └── test_workflows.py # Workflow tests
├── implementation/
│   └── progression.md   # Implementation tracker
├── run_tests.py        # Test runner script
├── pyproject.toml       # Python project config
├── README.md           # This file
└── .env.example        # Environment template
```

## Key Concepts

### Dual-Index Strategy
- **Central MOCs**: Maps of Content in `14-Maps-of-Content/` for each root category and subcategory
- **Local Domain Indexes**: Index files within each domain folder for local navigation
- **Generated markers**: `<!-- veltiosi:generated:start -->` markers identify generated sections

### Note Classification
- **Note types**: Concept, Source Summary, Compounding Page, Synthesis, MOC, Task Linked, Reference, Generated Index
- **Generated status**: Manual, Generated, Mixed (tracking of AI-generated content)
- **Slope sections**: Notes can have "slope" sections for tracking progress

### Architecture Principles
- **Modular Services**: Shared service layer for consistent vault access
- **LLM Fallback**: Google Gemini primary, configurable fallback, mock provider for testing
- **Dry-run Safety**: Every mutating command supports `--dry-run`
- **Review Queue**: Ambiguous task mappings go to review queue (never auto-apply)
- **Idempotency**: Cron-safe operation with no side effects on re-run
- **Test Coverage**: Comprehensive test suite with fixtures and mocks

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Code quality checks
ruff check src/
black src/

# Run tests
./run_tests.py
./run_tests.py --coverage
./run_tests.py --test tests/test_services.py --verbose

# Test LLM service
python -c "from src.veltiosi.services.llm_service import llm_service; print(llm_service.test_all_connections())"

# Run specific workflow
python -m src.veltiosi.workflows.wiki_query --interactive
python -m src.veltiosi.workflows.wiki_ingest test.txt --dry-run
python -m src.veltiosi.workflows.weekly_synthesis --dry-run
```

## License

MIT

## Acknowledgments

- Inspired by Karpathy's LLM Wiki pattern
- Built for integration with Hermes Agent / Satya
- Designed for sustainable knowledge compounding in Obsidian

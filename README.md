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

✅ **Milestone A**: Bootstrap & Configuration - Complete  
✅ **Milestone B**: Core Utilities & Connectors - Complete  
✅ **Milestone C**: Indexing & Classification - Complete  
🔜 **Milestone D**: Lint & Governance - Next  

**Implemented Features**:
- Vault scanning and note classification
- Backlink analysis and graph building
- Root category and subcategory index generation
- Dual-index strategy (central MOCs + local domain indexes)
- Audit logging with run tracking
- CLI interface with 8 commands
- Configuration system with YAML files

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

# System Information
veltiosi status                        # Show system status
veltiosi config-show                   # Show current configuration

# Coming Soon
veltiosi wiki-lint                     # Lint for health and consistency
veltiosi wiki-ingest <path_or_url>     # Ingest raw source
veltiosi task-sync --days 7            # Sync Atma task completions
veltiosi weekly-synthesis              # Generate weekly synthesis
veltiosi wiki-query "question"         # Query wiki with citations
```

### Example Workflow

```bash
# 1. Check current vault state
veltiosi status

# 2. Run consistency check
veltiosi wiki-index --check

# 3. Generate indexes (dry run first)
veltiosi wiki-index --dry-run
veltiosi wiki-index

# 4. Check generated indexes
ls ~/Obsidian/14-Maps-of-Content/
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
│   ├── indexing/          # Indexing & classification
│   │   ├── scanner.py    # Vault scanner
│   │   ├── classifier.py # Note classifier
│   │   ├── backlinks.py  # Backlink analysis
│   │   └── index_builder.py # Index builder
│   ├── workflows/        # Workflow orchestration
│   │   └── wiki_index.py # Indexing workflow
│   └── utils/           # Utility modules
│       ├── dates.py     # Date utilities
│       ├── markdown.py  # Markdown utilities
│       ├── text.py      # Text processing
│       └── ids.py       # ID generation
├── implementation/
│   └── progression.md   # Implementation tracker
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

### Safety Rules
- Every mutating command supports `--dry-run`
- Ambiguous task mappings go to review queue (never auto-apply)
- No silent overwrite of manually curated prose
- Idempotency required for cron-safe operation

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Code quality checks
ruff check src/
black src/

# Run tests (when available)
pytest tests/

# Run specific workflow
python -m veltiosi.cli wiki-index --check
```

## License

MIT

## Acknowledgments

- Inspired by Karpathy's LLM Wiki pattern
- Built for integration with Hermes Agent / Satya
- Designed for sustainable knowledge compounding in Obsidian

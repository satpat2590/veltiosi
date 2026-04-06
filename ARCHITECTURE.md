# Veltiosi Architecture

## System Overview

Veltiosi is an automation layer for Obsidian knowledge bases that implements a sustainable, compounding wiki system using Karpathy's LLM Wiki pattern.

```
┌─────────────────────────────────────────────────────────────┐
│                     User / Hermes Agent                     │
│                           (Satya)                           │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    Veltiosi CLI Interface                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────────┐  │
│  │ wiki-   │ │ wiki-   │ │ task-   │ │ weekly-          │  │
│  │ index   │ │ lint    │ │ sync    │ │ synthesis       │  │
│  └─────────┘ └─────────┘ └─────────┘ └──────────────────┘  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────────┐  │
│  │ wiki-   │ │ config- │ │ status  │ │                  │  │
│  │ ingest  │ │ show    │ │         │ │                  │  │
│  └─────────┘ └─────────┘ └─────────┘ └──────────────────┘  │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    Workflow Orchestration                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ wiki_index   │ │ wiki_lint    │ │ task_sync    │ ...    │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Engine Components                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ Indexing &   │ │ Audit &      │ │ Connectors   │        │
│  │ Classification│ │ Review Queue │ │ (External    │        │
│  └──────────────┘ └──────────────┘ │  Services)   │        │
│                                     └──────────────┘        │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Obsidian   │ │     Atma     │ │   Google     │
│    Vault     │ │   (Tasks)    │ │   Gemini     │
│  (~/Obsidian)│ │              │ │    (LLM)     │
└──────────────┘ └──────────────┘ └──────────────┘
```

## Component Details

### 1. CLI Interface (`src/veltiosi/cli.py`)
- Built with Typer and Rich for beautiful CLI output
- 8 commands covering all major workflows
- Supports `--dry-run`, `--check`, `--json` output options
- Integrated with audit system for operation tracking

### 2. Workflow Orchestration (`src/veltiosi/workflows/`)
- **`wiki_index.py`**: Complete indexing workflow (scan → classify → backlinks → build indexes)
- Future workflows: `wiki_lint.py`, `task_sync.py`, `weekly_synthesis.py`, `wiki_ingest.py`, `wiki_query.py`

### 3. Indexing & Classification (`src/veltiosi/indexing/`)
- **`scanner.py`**: Discovers and analyzes notes in vault, extracts metadata
- **`classifier.py`**: Categorizes notes into root categories and subcategories using keyword matching
- **`backlinks.py`**: Builds graph of note relationships, analyzes connectivity
- **`index_builder.py`**: Generates MOCs and indexes using dual-index strategy

### 4. Connectors (`src/veltiosi/connectors/`)
- **`obsidian.py`**: Read/write operations on Obsidian vault, note statistics
- **`atma.py`**: Task fetching and mapping from Atma system
- **`gemini.py`**: Google Gemini LLM integration for content generation
- **`hermes.py`**: Hermes Agent integration for skill and profile management

### 5. Audit System (`src/veltiosi/audit.py`)
- JSON-based audit logging with run tracking
- Review queue for ambiguous task mappings
- Statistics and reporting capabilities
- Directory: `~/.veltiosi/audit/`

### 6. Utilities (`src/veltiosi/utils/`)
- **`dates.py`**: Date parsing and formatting
- **`markdown.py`**: Markdown parsing and manipulation
- **`text.py`**: Text processing and keyword extraction
- **`ids.py`**: ID generation and validation

## Data Flow

### Indexing Workflow
```
1. Scan vault → Discover all .md files
2. Extract metadata → Note type, domain folder, wikilinks
3. Classify notes → Root categories, subcategories
4. Build backlink graph → Calculate wikilinks_in
5. Generate indexes → MOCs, domain indexes, master index
6. Write to disk → With generated markers
7. Audit log → Record operation statistics
```

### Dual-Index Strategy
```
Central MOCs (14-Maps-of-Content/):
  - Physical MOC.md
  - Mental MOC.md
  - Financial MOC.md
  - Social MOC.md
  - Health MOC.md
  - Trading Systems MOC.md
  - ...

Local Domain Indexes (within each folder):
  - 15-Daily-Notes/Health Index.md
  - 08-Edoras/Trading Systems Index.md
  - 04-Language/Language Learning Index.md
  - ...
```

## Configuration System

### Environment Variables (`.env`)
```
VELTIOSI_OBSIDIAN_VAULT=/home/satyamini/Obsidian
GOOGLE_API_KEY=...
ATMA_BASE_URL=...
ATMA_API_KEY=...
```

### YAML Configuration Files (`config/`)
1. **`categories.yaml`**: Root categories with display names, MOC paths, colors
2. **`subcategories.yaml`**: Subcategories with primary roots, domain folders
3. **`domain_map.yaml`**: Domain folder to root category mapping
4. **`task_rules.yaml`**: Pattern-based task mapping rules
5. **`generation_rules.yaml`**: Safety rules and generation parameters
6. **`llm.yaml`**: LLM provider configuration and prompts

## Data Models

### NoteRecord (`src/veltiosi/models.py`)
- Core note metadata: path, title, domain_folder, note_type
- Classification: primary_root_category, secondary_root_categories, subcategories
- Content analysis: wikilinks_out, wikilinks_in, has_slope_section, generated_status
- Metadata: created_at, modified_at, file_size, line_count

### AuditEvent
- Run tracking: run_id, timestamp, command, mode, status
- Statistics: notes_read, notes_written, review_items_created
- Diagnostics: warnings, errors, duration_seconds

### ReviewQueueItem
- Ambiguous task mappings for manual review
- Task metadata, ambiguity reason, proposed mappings
- Status tracking: pending, approved, denied, modified, resolved

## Safety & Idempotency

### Safety Rules
1. **Dry-run support**: All mutating commands support `--dry-run`
2. **Review queue**: Ambiguous task mappings never auto-apply
3. **Generated markers**: AI-generated content clearly marked
4. **No silent overwrites**: Manual content preserved
5. **Audit trails**: All operations logged

### Idempotency
- Index generation can be run multiple times safely
- Generated sections identified with markers for safe updates
- Task processing tracks already-processed tasks
- Cron-safe operation for scheduled runs

## Integration Points

### Obsidian Vault
- Reads existing note structure and content
- Writes generated indexes with clear markers
- Preserves existing domain folder structure
- Respects ignored paths configuration

### Hermes Agent
- Skill registration for CLI commands
- Profile configuration with environment variables
- Cron job setup for scheduled operations
- Operating interface through Satya persona

### External Services
- **Google Gemini**: Content generation, query answering, analysis
- **Atma**: Task completion fetching and mapping
- Future: Web scraping, API integrations, data sources

## Performance Considerations

- **Vault scanning**: Optimized for large vaults with incremental scanning
- **Content analysis**: Limits content reading for performance
- **Graph building**: Efficient backlink calculation
- **Index generation**: Template-based for consistency
- **Audit logging**: JSON files for easy querying

## Extension Points

### Plugin Architecture
1. **Domain plugins**: Specialized logic for specific domains (Edoras/finance, Poetry/creative)
2. **Source handlers**: Custom ingestion for different source types
3. **Export formats**: Additional output formats beyond markdown
4. **Analysis modules**: Advanced analytics and visualization

### Custom Classifiers
- Rule-based classification extensions
- Machine learning classifiers for note types
- Custom keyword sets for specialized domains
- Integration with external classification services
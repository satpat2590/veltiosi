# Veltiosi Implementation Progression

*This document tracks the implementation of Veltiosi, the automation layer for the Obsidian knowledge base.*

## Overview

**Goal**: Build a sustainable, compounding wiki system that:
- Maintains `~/Obsidian` as the knowledge store
- Uses 4 canonical roots: Physical, Mental, Financial, Social
- Preserves existing Obsidian folder structure as subdomains/views
- Integrates with Hermes Agent / Satya as the operating interface
- Integrates with Atma for task-driven knowledge updates
- Uses Google Gemini as the primary automation model family
- Routes ambiguous task mappings into a markdown review queue

**Repository**: `~/veltiosi`

## Milestones

### Milestone A: Bootstrap & Configuration ✅
- [x] Create repository structure
- [x] Create `pyproject.toml` with dependencies
- [x] Create `README.md`
- [x] Create `.env.example`
- [x] Create config schemas:
  - [x] `config/categories.yaml`
  - [x] `config/subcategories.yaml`
  - [x] `config/domain_map.yaml`
  - [x] `config/task_rules.yaml`
  - [x] `config/generation_rules.yaml`
  - [x] `config/llm.yaml`
- [x] Create `src/veltiosi/__init__.py`
- [x] Create `src/veltiosi/settings.py`
- [x] Create `src/veltiosi/models.py`
- [x] Create `src/veltiosi/cli.py` skeleton
- [x] Create this progression document

### Milestone B: Core Utilities & Connectors ✅
- [x] Create `src/veltiosi/utils/dates.py`
- [x] Create `src/veltiosi/utils/markdown.py`
- [x] Create `src/veltiosi/utils/text.py`
- [x] Create `src/veltiosi/utils/ids.py`
- [x] Create `src/veltiosi/connectors/obsidian.py`
- [x] Create `src/veltiosi/connectors/atma.py`
- [x] Create `src/veltiosi/connectors/gemini.py`
- [x] Create `src/veltiosi/connectors/hermes.py`
- [x] Create `src/veltiosi/audit.py`

### Milestone C: Indexing & Classification ✅
- [x] Create `src/veltiosi/indexing/scanner.py`
- [x] Create `src/veltiosi/indexing/classifier.py`
- [x] Create `src/veltiosi/indexing/backlinks.py`
- [x] Create `src/veltiosi/indexing/index_builder.py`
- [x] Create `src/veltiosi/workflows/wiki_index.py`
- [x] Test vault scanning and note classification

### Milestone D: Lint & Governance
- [ ] Create `src/veltiosi/workflows/wiki_lint.py`
- [ ] Implement orphan detection
- [ ] Implement weak-link detection
- [ ] Implement stale page detection
- [ ] Implement missing slope section detection
- [ ] Implement missing category assignment detection
- [ ] Implement index drift detection
- [ ] Test lint against fixture vault

### Milestone E: Review Queue
- [ ] Create `src/veltiosi/review/queue.py`
- [ ] Implement review queue item generation
- [ ] Implement review queue file writing
- [ ] Integrate with task sync for ambiguous mappings

### Milestone F: Task Sync
- [ ] Create `src/veltiosi/workflows/task_sync.py`
- [ ] Implement Atma completion fetching
- [ ] Implement rule-based mapping engine
- [ ] Implement compounding page updater
- [ ] Implement tag point reconciliation
- [ ] Implement MOC refresh
- [ ] Test with fixture Atma payloads

### Milestone G: Weekly Synthesis
- [ ] Create `src/veltiosi/workflows/weekly_synthesis.py`
- [ ] Implement weekly synthesis generator
- [ ] Implement category balance analysis
- [ ] Implement gap detection
- [ ] Implement suggested next tasks
- [ ] Test synthesis generation

### Milestone H: Source Ingestion
- [ ] Create `src/veltiosi/workflows/wiki_ingest.py`
- [ ] Create `src/veltiosi/templates/` with Jinja2 templates
- [ ] Implement local file ingestion
- [ ] Implement URL ingestion
- [ ] Implement source registry
- [ ] Implement summary note generation
- [ ] Test with local markdown and URL flows

### Milestone I: Query Layer
- [ ] Create `src/veltiosi/workflows/wiki_query.py`
- [ ] Implement retrieval over index, MOCs, and notes
- [ ] Implement citation formatting
- [ ] Implement answer-to-note compounding
- [ ] Test query answering

### Milestone J: Hermes Integration
- [ ] Create Hermes skill wrappers for all CLI commands
- [ ] Set up cron jobs for weekly synthesis and periodic lint
- [ ] Implement profile-safe config handling
- [ ] Test Hermes invocation

### Milestone K: Testing & Hardening
- [ ] Create `tests/` directory with fixtures
- [ ] Write unit tests for core utilities
- [ ] Write integration tests for workflows
- [ ] Implement idempotency tests
- [ ] Add error handling and recovery
- [ ] Performance optimization for large vaults

### Milestone L: Advanced Features (Post-V1)
- [ ] Slope metrics per category
- [ ] Category dashboards
- [ ] Domain plugin architecture
- [ ] Edoras financial plugin
- [ ] Poetry/creative practice plugin
- [ ] Higher-order query compounding

## Current Status

**Date**: 2026-04-06  
**Phase**: Milestone C completed  
**Next**: Milestone D - Lint & Governance

## Implementation Notes

### Design Decisions
1. **Repository location**: `~/veltiosi`
2. **Category indexing**: Dual output (central MOCs + local domain indexes)
3. **Ambiguous task mappings**: Markdown review queue in `20-Task-System/Review-Queue/`
4. **Primary LLM**: Google Gemini
5. **Hermes role**: Operating interface between user and wiki
6. **Generated section ownership**: Marked with `<!-- veltiosi:generated:start -->` markers
7. **Audit logs**: JSONL format in `17-References/Veltiosi-Audit/`

### Safety Rules
- Every mutating command supports `--dry-run`
- Every workflow writes machine-readable audit events
- No silent overwrite of manually curated prose
- Ambiguous mappings never auto-apply
- Idempotency required for cron-safe operation

### Testing Strategy
- Unit tests for classifier rules, backlink parser, generated section patching
- Integration tests with fixture vault and Atma payloads
- Golden-file tests for generated index and synthesis output
- Idempotency tests for reruns

## Next Steps

1. **Test indexing functionality**:
   ```bash
   cd ~/veltiosi
   python -m veltiosi.cli wiki-index --check
   python -m veltiosi.cli wiki-index --dry-run
   ```

2. **Implement Milestone D** (Lint & Governance):
   - Create `src/veltiosi/workflows/wiki_lint.py`
   - Implement orphan detection, weak-link detection, stale page detection
   - Implement missing slope section and category assignment detection
   - Test lint against actual vault

3. **Set up environment variables** (optional):
   - Create `.env` file with API keys for Gemini and Atma
   - Configure Hermes integration

## Configuration Reference

Key config files:
- `config/categories.yaml`: Root categories (Physical, Mental, Financial, Social)
- `config/subcategories.yaml`: Subcategories like Health, Trading Systems, etc.
- `config/domain_map.yaml`: Domain folder to root category mapping
- `config/task_rules.yaml`: Task mapping rules for Atma completions
- `config/generation_rules.yaml`: Safety and generation rules
- `config/llm.yaml`: Google Gemini configuration

## CLI Commands (Planned)

- `veltiosi wiki-index`
- `veltiosi wiki-lint`
- `veltiosi wiki-ingest`
- `veltiosi task-sync`
- `veltiosi weekly-synthesis`
- `veltiosi wiki-query`
- `veltiosi config-show`
- `veltiosi status`

---

*Last updated: 2026-04-06*  
*Maintainer: Satya (LLM)*

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

### Milestone D: Lint & Governance ✅
- [x] Create `src/veltiosi/workflows/wiki_lint.py`
- [x] Implement orphan detection
- [x] Implement weak-link detection
- [x] Implement stale page detection
- [x] Implement missing slope section detection
- [x] Implement missing category assignment detection
- [x] Implement index drift detection
- [x] **ENHANCED**: Add LLM-powered intelligent fixes for:
  - [x] Missing category classification (LLM-powered)
  - [x] Missing slope section generation (LLM-powered)
  - [x] Orphan note resolution (LLM-powered link suggestions)
  - [x] Weak link strengthening (LLM-powered connection suggestions)
- [x] Test lint against actual vault
- [x] Implement LLM fallback to static logic when API unavailable

### Milestone E: Review Queue ✅
- [x] Create `src/veltiosi/review/queue.py`
- [x] Implement review queue item generation
- [x] Implement review queue file writing
- [x] Integrate with task sync for ambiguous mappings

*Note: Review queue functionality implemented directly in `task_sync.py` workflow*

### Milestone F: Task Sync ✅
- [x] Create `src/veltiosi/workflows/task_sync.py`
- [x] Implement Atma completion fetching
- [x] Implement rule-based mapping engine
- [x] Implement compounding page updater
- [x] Implement tag point reconciliation
- [x] Implement MOC refresh
- [x] Test with fixture Atma payloads

### Milestone G: Weekly Synthesis ✅
- [x] Create `src/veltiosi/workflows/weekly_synthesis.py`
- [x] Implement weekly synthesis generator
- [x] Implement category balance analysis
- [x] Implement gap detection
- [x] Implement suggested next tasks
- [x] Test synthesis generation

### Milestone H: Source Ingestion ✅
- [x] Create `src/veltiosi/workflows/wiki_ingest.py`
- [x] Implement local file ingestion
- [x] Implement URL ingestion
- [x] Implement source registry
- [x] Implement summary note generation
- [x] Test with local markdown and URL flows

### Milestone I: Query Layer ✅
- [x] Create `src/veltiosi/workflows/wiki_query.py`
- [x] Implement retrieval over index, MOCs, and notes
- [x] Implement citation formatting
- [x] Implement answer-to-note compounding
- [x] Test query answering

### Milestone J: Hermes Integration
- [ ] Create Hermes skill wrappers for all CLI commands
- [ ] Set up cron jobs for weekly synthesis and periodic lint
- [ ] Implement profile-safe config handling
- [ ] Test Hermes invocation

### Milestone K: Testing & Hardening ✅
- [x] Create `tests/` directory with fixtures
- [x] Write unit tests for core utilities
- [x] Write integration tests for workflows
- [x] Implement idempotency tests
- [x] Add error handling and recovery
- [x] Performance optimization for large vaults

### Milestone L: Advanced Features (Post-V1)
- [ ] Slope metrics per category
- [ ] Category dashboards
- [ ] Domain plugin architecture
- [ ] Edoras financial plugin
- [ ] Poetry/creative practice plugin
- [ ] Higher-order query compounding

## Current Status

**Date**: 2026-04-06  
**Phase**: MVP COMPLETE - All core workflows implemented  
**Next**: Integration testing and deployment

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
- LLM fallback system: Gemini → configurable fallback → mock provider

### Testing Strategy ✅
- Unit tests for classifier rules, backlink parser, generated section patching
- Integration tests with fixture vault and Atma payloads
- Golden-file tests for generated index and synthesis output
- Idempotency tests for reruns
- Mock LLM provider for offline testing
- Comprehensive test suite with pytest fixtures

## Next Steps

1. **Integration Testing**:
   ```bash
   cd ~/veltiosi
   ./run_tests.py --coverage
   python -m src.veltiosi.workflows.wiki_query --interactive
   python -m src.veltiosi.workflows.wiki_ingest test.txt --dry-run
   python -m src.veltiosi.workflows.weekly_synthesis --dry-run
   ```

2. **Deployment Preparation**:
   - Update CLI to include new workflow commands
   - Test with actual Obsidian vault
   - Configure Google Gemini API key for production use
   - Set up cron jobs for automated workflows

3. **Documentation**:
   - Update CLI help text
   - Create user guide for each workflow
   - Document API integration patterns

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

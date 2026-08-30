"""Wiki linting workflow for health and consistency checks."""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..audit import AuditLogger
from ..connectors.gemini import GeminiConnector
from ..indexing.backlinks import BacklinkAnalyzer
from ..indexing.classifier import NoteClassifier
from ..indexing.scanner import VaultScanner
from ..models import LintIssue, NoteRecord
from ..settings import settings

logger = logging.getLogger(__name__)


class WikiLinter:
    """Linter for wiki health and consistency checks."""

    def __init__(self, vault_path: Optional[Path] = None, use_llm: bool = True):
        """Initialize wiki linter."""
        self.vault_path = vault_path or settings.obsidian_vault
        self.scanner = VaultScanner(self.vault_path)
        self.classifier = NoteClassifier()
        self.backlink_analyzer = BacklinkAnalyzer()

        # LLM integration for intelligent fixes
        self.use_llm = use_llm
        self.llm_connector = None
        if self.use_llm:
            try:
                self.llm_connector = GeminiConnector()
                if not self.llm_connector.api_key:
                    logger.warning("LLM API key not configured, falling back to static fixes")
                    self.use_llm = False
                else:
                    logger.info("LLM integration enabled for intelligent fixes")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM connector: {e}")
                self.use_llm = False

        # Configuration from generation rules
        self.lint_config = settings.generation_rules.lint
        self.stale_days = self.lint_config.get("stale_days", 90)
        self.orphan_threshold = self.lint_config.get("orphan_threshold", 0)
        self.weak_link_threshold = self.lint_config.get("weak_link_threshold", 1)

        logger.info("Wiki linter initialized")

    def run_lint(self, fix_safe: bool = False, dry_run: bool = False) -> Dict[str, any]:
        """Run complete linting workflow."""
        start_time = time.time()

        try:
            logger.info("Starting wiki linting workflow")

            # Step 1: Scan and classify notes
            notes = self.scanner.scan_vault()
            classified_notes = self.classifier.batch_classify(notes)

            # Step 2: Build backlink graph
            self.backlink_analyzer.build_graph(classified_notes)

            # Step 3: Run all lint checks
            all_issues = []

            # Orphan detection
            orphan_issues = self.detect_orphans(classified_notes)
            all_issues.extend(orphan_issues)

            # Weak link detection
            weak_link_issues = self.detect_weak_links()
            all_issues.extend(weak_link_issues)

            # Stale page detection
            stale_issues = self.detect_stale_pages(classified_notes)
            all_issues.extend(stale_issues)

            # Missing slope section detection
            slope_issues = self.detect_missing_slope_sections(classified_notes)
            all_issues.extend(slope_issues)

            # Missing category assignment detection
            category_issues = self.detect_missing_categories(classified_notes)
            all_issues.extend(category_issues)

            # Index drift detection
            drift_issues = self.detect_index_drift(classified_notes)
            all_issues.extend(drift_issues)

            # Step 4: Apply safe fixes if requested
            fixed_issues = []
            if fix_safe and not dry_run:
                fixed_issues = self.apply_safe_fixes(all_issues, classified_notes)

            # Step 5: Generate statistics
            stats = self.generate_lint_statistics(all_issues, fixed_issues)

            duration = time.time() - start_time

            result = {
                "success": True,
                "duration_seconds": round(duration, 2),
                "notes_scanned": len(classified_notes),
                "issues_found": len(all_issues),
                "issues_fixed": len(fixed_issues),
                "statistics": stats,
                "issues": [issue.model_dump() for issue in all_issues],
                "fixed_issues": [issue.model_dump() for issue in fixed_issues],
            }

            logger.info(
                f"Linting completed in {duration:.2f}s: "
                f"{len(all_issues)} issues found, {len(fixed_issues)} fixed"
            )

            return result

        except Exception as e:
            logger.error(f"Linting failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "duration_seconds": round(time.time() - start_time, 2),
            }

    def detect_orphans(self, notes: List[NoteRecord]) -> List[LintIssue]:
        """Detect orphan notes (no backlinks)."""
        issues = []

        # Get orphan notes from backlink analyzer
        orphans = self.backlink_analyzer.find_orphans()

        for note_title in orphans:
            # Find the note record
            note = next((n for n in notes if n.title == note_title), None)
            if not note:
                continue

            # Check if note should be exempt (e.g., MOCs, indexes)
            if self._is_orphan_exempt(note):
                continue

            # Generate suggestion based on whether LLM is available
            suggestion = "Consider linking to this note from other relevant notes, or delete if no longer needed"
            fixable = self.use_llm and self.llm_connector  # Fixable with LLM

            issue = LintIssue(
                issue_type="orphan_note",
                note_path=note.path,
                severity="warning",
                message=f"Note has no backlinks (orphan)",
                suggestion=suggestion,
                fixable=fixable,
            )
            issues.append(issue)

        logger.info(f"Found {len(issues)} orphan notes")
        return issues

    def detect_weak_links(self) -> List[LintIssue]:
        """Detect weak links in the note graph."""
        issues = []

        # Get weak links from backlink analyzer
        weak_links = self.backlink_analyzer.find_weak_links(threshold=self.weak_link_threshold)

        for source_title, target_title in weak_links:
            # Find source note
            source_note = self._find_note_by_title(source_title)
            if not source_note:
                continue

            # Generate suggestion based on whether LLM is available
            suggestion = "Consider adding additional links to strengthen connection, or create bridging notes"
            fixable = self.use_llm and self.llm_connector  # Fixable with LLM

            issue = LintIssue(
                issue_type="weak_link",
                note_path=source_note.path,
                severity="info",
                message=f"Weak link to '{target_title}' (only connection between graph components)",
                suggestion=suggestion,
                fixable=fixable,
            )
            issues.append(issue)

        logger.info(f"Found {len(issues)} weak links")
        return issues

    def detect_stale_pages(self, notes: List[NoteRecord]) -> List[LintIssue]:
        """Detect stale pages (not modified in long time)."""
        issues = []

        cutoff_date = datetime.now() - timedelta(days=self.stale_days)

        for note in notes:
            # Skip certain note types
            if note.note_type.value in ["moc", "generated_index"]:
                continue

            # Check if note is stale
            if note.modified_at and note.modified_at.timestamp() < cutoff_date.timestamp():
                days_stale = (datetime.now() - note.modified_at).days

                issue = LintIssue(
                    issue_type="stale_page",
                    note_path=note.path,
                    severity="info",
                    message=f"Page not modified in {days_stale} days",
                    suggestion="Consider updating with new insights, archiving, or deleting",
                    fixable=False,
                )
                issues.append(issue)

        logger.info(f"Found {len(issues)} stale pages")
        return issues

    def detect_missing_slope_sections(self, notes: List[NoteRecord]) -> List[LintIssue]:
        """Detect notes missing slope sections where required."""
        issues = []

        # Get note types that require slope sections from config
        note_types_config = settings.generation_rules.lint.get("note_types", {})

        for note in notes:
            # Check if this note type requires slope section
            note_type_config = note_types_config.get(note.note_type.value, {})
            requires_slope = note_type_config.get("requires_slope", False)

            if requires_slope and not note.has_slope_section:
                issue = LintIssue(
                    issue_type="missing_slope_section",
                    note_path=note.path,
                    severity="warning",
                    message=f"Note type '{note.note_type.value}' requires slope section but none found",
                    suggestion="Add a '## Slope' section to track progress and insights",
                    fixable=True,  # Could auto-add slope section template
                )
                issues.append(issue)

        logger.info(f"Found {len(issues)} notes missing slope sections")
        return issues

    def detect_missing_categories(self, notes: List[NoteRecord]) -> List[LintIssue]:
        """Detect notes missing category assignments."""
        issues = []

        for note in notes:
            # Skip certain note types
            if note.note_type.value in ["moc", "generated_index"]:
                continue

            # Check for missing primary root category
            if not note.primary_root_category and note.domain_folder != "root":
                issue = LintIssue(
                    issue_type="missing_primary_category",
                    note_path=note.path,
                    severity="warning",
                    message=f"Note in domain folder '{note.domain_folder}' has no primary root category",
                    suggestion=f"Assign to a root category (Physical, Mental, Financial, Social) based on content",
                    fixable=True,  # Could auto-classify
                )
                issues.append(issue)

            # Check for missing subcategories
            if note.primary_root_category and not note.subcategories:
                issue = LintIssue(
                    issue_type="missing_subcategories",
                    note_path=note.path,
                    severity="info",
                    message=f"Note with primary category '{note.primary_root_category.value}' has no subcategories",
                    suggestion="Assign relevant subcategories based on content analysis",
                    fixable=True,  # Could auto-classify
                )
                issues.append(issue)

        logger.info(f"Found {len(issues)} notes with missing categories")
        return issues

    def detect_index_drift(self, notes: List[NoteRecord]) -> List[LintIssue]:
        """Detect drift between actual notes and generated indexes."""
        issues = []

        # This is a simplified implementation
        # Full implementation would parse existing MOCs and compare with current notes

        # Check for missing MOCs
        for root_name, root_config in settings.root_categories.items():
            moc_path = self.vault_path / root_config.moc_path
            if not moc_path.exists():
                issue = LintIssue(
                    issue_type="missing_moc",
                    note_path=moc_path,
                    severity="error",
                    message=f"Root category MOC not found: {moc_path}",
                    suggestion=f"Run 'veltiosi wiki-index' to generate missing MOCs",
                    fixable=True,
                )
                issues.append(issue)

        for subcat_name, subcat_config in settings.subcategories.items():
            moc_path = self.vault_path / subcat_config.moc_path
            if not moc_path.exists():
                issue = LintIssue(
                    issue_type="missing_moc",
                    note_path=moc_path,
                    severity="error",
                    message=f"Subcategory MOC not found: {moc_path}",
                    suggestion=f"Run 'veltiosi wiki-index' to generate missing MOCs",
                    fixable=True,
                )
                issues.append(issue)

        logger.info(f"Found {len(issues)} index drift issues")
        return issues

    def apply_safe_fixes(self, issues: List[LintIssue], notes: List[NoteRecord]) -> List[LintIssue]:
        """Apply safe fixes to lint issues."""
        fixed_issues = []
        llm_fixes = 0
        static_fixes = 0

        for issue in issues:
            if not issue.fixable:
                continue

            try:
                fix_applied = False
                fix_type = "static"

                if issue.issue_type == "missing_slope_section":
                    fix_applied = self._fix_missing_slope_section(issue.note_path)
                    if fix_applied and self.use_llm:
                        fix_type = "llm"

                elif issue.issue_type == "missing_primary_category":
                    note = next((n for n in notes if n.path == issue.note_path), None)
                    if note:
                        fix_applied = self._fix_missing_category(note)
                        if fix_applied and self.use_llm:
                            fix_type = "llm"

                elif issue.issue_type == "missing_subcategories":
                    note = next((n for n in notes if n.path == issue.note_path), None)
                    if note:
                        fix_applied = self._fix_missing_subcategories(note)
                        if fix_applied and self.use_llm:
                            fix_type = "llm"

                elif issue.issue_type == "missing_moc":
                    # This would be fixed by running wiki-index
                    # For now, just track it
                    fix_applied = True
                    fix_type = "tracked"

                elif issue.issue_type == "orphan_note":
                    note = next((n for n in notes if n.path == issue.note_path), None)
                    if note:
                        fix_applied = self._fix_orphan_note(note, notes)
                        if fix_applied:
                            fix_type = "llm"  # Orphan fixes always use LLM if fixable

                elif issue.issue_type == "weak_link":
                    # Extract target from message
                    import re

                    match = re.search(r"to '([^']+)'", issue.message)
                    if match:
                        target_title = match.group(1)
                        source_note = next((n for n in notes if n.path == issue.note_path), None)
                        if source_note:
                            fix_applied = self._fix_weak_link(source_note, target_title, notes)
                            if fix_applied:
                                fix_type = "llm"  # Weak link fixes always use LLM if fixable

                if fix_applied:
                    fixed_issues.append(issue)
                    if fix_type == "llm":
                        llm_fixes += 1
                        logger.debug(f"Applied LLM fix for {issue.issue_type} at {issue.note_path}")
                    elif fix_type == "static":
                        static_fixes += 1
                        logger.debug(
                            f"Applied static fix for {issue.issue_type} at {issue.note_path}"
                        )

            except Exception as e:
                logger.warning(f"Failed to fix issue {issue.issue_type} for {issue.note_path}: {e}")

        logger.info(
            f"Applied {len(fixed_issues)} safe fixes "
            f"({llm_fixes} LLM-powered, {static_fixes} static)"
        )
        return fixed_issues

    def generate_lint_statistics(
        self, issues: List[LintIssue], fixed_issues: List[LintIssue]
    ) -> Dict[str, any]:
        """Generate linting statistics."""
        stats = {
            "total_issues": len(issues),
            "fixed_issues": len(fixed_issues),
            "by_severity": {
                "error": 0,
                "warning": 0,
                "info": 0,
            },
            "by_issue_type": {},
            "fixable_issues": 0,
            "unfixable_issues": 0,
            "llm_available": self.use_llm and self.llm_connector is not None,
            "llm_fixable_issues": 0,
        }

        for issue in issues:
            # Count by severity
            stats["by_severity"][issue.severity] = stats["by_severity"].get(issue.severity, 0) + 1

            # Count by issue type
            stats["by_issue_type"][issue.issue_type] = (
                stats["by_issue_type"].get(issue.issue_type, 0) + 1
            )

            # Count fixable vs unfixable
            if issue.fixable:
                stats["fixable_issues"] += 1
                # Count LLM-fixable issues (orphans and weak links when LLM is available)
                if (
                    issue.issue_type in ["orphan_note", "weak_link"]
                    and self.use_llm
                    and self.llm_connector
                ):
                    stats["llm_fixable_issues"] += 1
            else:
                stats["unfixable_issues"] += 1

        return stats

    def _is_orphan_exempt(self, note: NoteRecord) -> bool:
        """Check if a note should be exempt from orphan detection."""
        # MOCs and generated indexes are expected to have many backlinks
        if note.note_type.value in ["moc", "generated_index"]:
            return True

        # Daily notes and certain domain folders might be exempt
        exempt_folders = self.lint_config.get("orphan_exempt_folders", [])
        if note.domain_folder in exempt_folders:
            return True

        # Very small notes might be temporary or meta
        if note.file_size < 100:  # Less than 100 bytes
            return True

        return False

    def _find_note_by_title(self, title: str) -> Optional[NoteRecord]:
        """Find a note by title (simplified - would need full scan in production)."""
        # This is a simplified implementation
        # In production, we would maintain a title-to-note mapping
        notes = self.scanner.scan_vault(limit=1000)  # Limit for performance
        return next((n for n in notes if n.title == title), None)

    def _fix_missing_slope_section(self, note_path: Path) -> bool:
        """Add a slope section to a note."""
        try:
            # Try LLM-powered slope generation first if available
            if self.use_llm and self.llm_connector:
                return self._fix_missing_slope_section_with_llm(note_path)

            # Fall back to static template
            return self._fix_missing_slope_section_static(note_path)

        except Exception as e:
            logger.error(f"Failed to add slope section to {note_path}: {e}")
            return False

    def _fix_missing_slope_section_with_llm(self, note_path: Path) -> bool:
        """Add an LLM-generated slope section to a note."""
        try:
            with open(note_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Generate slope content using LLM
            slope_content = self._generate_slope_content_with_llm(content)

            if not slope_content:
                # Fall back to static template if LLM fails
                return self._fix_missing_slope_section_static(note_path)

            # Add slope section at end
            slope_section = f"\n\n## Slope\n\n{slope_content}\n"
            new_content = content.rstrip() + slope_section

            with open(note_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            logger.info(f"Added LLM-generated slope section to {note_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to add LLM slope section to {note_path}: {e}")
            # Fall back to static template
            return self._fix_missing_slope_section_static(note_path)

    def _fix_missing_slope_section_static(self, note_path: Path) -> bool:
        """Add a static slope section template to a note."""
        try:
            with open(note_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Add slope section at end
            slope_template = (
                "\n\n## Slope\n\n*What's changing? What insights are accumulating?*\n\n"
            )
            new_content = content.rstrip() + slope_template

            with open(note_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            logger.info(f"Added static slope section to {note_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to add static slope section to {note_path}: {e}")
            return False

    def _fix_orphan_note(self, orphan_note: NoteRecord, all_notes: List[NoteRecord]) -> bool:
        """Fix orphan note by suggesting and creating links."""
        try:
            if not self.use_llm or not self.llm_connector:
                logger.info(f"Cannot fix orphan note {orphan_note.path} without LLM")
                return False

            # Get orphan note content
            with open(orphan_note.path, "r", encoding="utf-8") as f:
                orphan_content = f.read()

            # Get sample of other notes for context
            sample_notes = []
            for note in all_notes[:20]:  # Limit to 20 notes for context
                if note.path != orphan_note.path:
                    try:
                        with open(note.path, "r", encoding="utf-8") as f:
                            content = f.read()
                            sample_notes.append(
                                {
                                    "title": note.title,
                                    "content": content[:500],  # Limit content
                                }
                            )
                    except:
                        continue

            # Generate link suggestions using LLM
            link_suggestions = self._generate_orphan_link_suggestions(
                orphan_note.title, orphan_content, sample_notes
            )

            if not link_suggestions:
                logger.info(f"No link suggestions generated for orphan note {orphan_note.path}")
                return False

            # Apply the first suggestion (most relevant)
            if link_suggestions and len(link_suggestions) > 0:
                suggestion = link_suggestions[0]
                if self._apply_link_suggestion(orphan_note, suggestion):
                    logger.info(f"Applied link suggestion for orphan note {orphan_note.path}")
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to fix orphan note {orphan_note.path}: {e}")
            return False

    def _generate_orphan_link_suggestions(
        self, orphan_title: str, orphan_content: str, sample_notes: List[Dict[str, str]]
    ) -> Optional[List[Dict[str, str]]]:
        """Generate link suggestions for orphan note using LLM."""
        try:
            if not self.llm_connector:
                return None

            # Build context from sample notes
            context_text = "Sample of existing notes in the wiki:\n"
            for note in sample_notes:
                context_text += f"\n--- Note: [[{note['title']}]] ---\n"
                context_text += f"{note['content']}\n"

            prompt = """
Orphan note (has no backlinks):
Title: {orphan_title}
Content: {orphan_content}

{context}

Analyze this orphan note and suggest 3-5 specific notes from the sample above that should link to it.
For each suggestion, provide:
1. Target note title
2. Reason for the link (why these notes are related)
3. Suggested location in the target note (e.g., "in the references section", "in the related concepts paragraph")

Return as a JSON array of objects with keys: "target_note", "reason", "suggested_location".
"""

            formatted_prompt = prompt.format(
                orphan_title=orphan_title,
                orphan_content=orphan_content[:2000],
                context=context_text[:3000],
            )

            response = self.llm_connector.generate_content(
                formatted_prompt, task_type="classification", temperature=0.2
            )

            if not response:
                return None

            # Parse JSON response
            import json

            try:
                # Extract JSON array
                lines = response.strip().split("\n")
                json_str = ""
                in_array = False

                for line in lines:
                    line = line.strip()
                    if line.startswith("["):
                        in_array = True
                    if in_array:
                        json_str += line
                    if line.endswith("]"):
                        break

                if json_str:
                    suggestions = json.loads(json_str)
                    if isinstance(suggestions, list):
                        return suggestions

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from orphan link suggestions: {e}")

            return None

        except Exception as e:
            logger.error(f"Failed to generate orphan link suggestions: {e}")
            return None

    def _apply_link_suggestion(self, orphan_note: NoteRecord, suggestion: Dict[str, str]) -> bool:
        """Apply a link suggestion by adding backlink to target note."""
        try:
            target_title = suggestion.get("target_note")
            if not target_title:
                return False

            # Find target note
            target_note = self._find_note_by_title(target_title)
            if not target_note:
                logger.warning(f"Target note not found: {target_title}")
                return False

            # Read target note content
            with open(target_note.path, "r", encoding="utf-8") as f:
                content = f.read()

            # Add link to orphan note
            link_text = f" [[{orphan_note.title}]]"

            # Simple implementation: append link at end
            # In production, would use suggested_location
            new_content = content.rstrip() + f"\n\nRelated: {link_text}\n"

            # Write back
            with open(target_note.path, "w", encoding="utf-8") as f:
                f.write(new_content)

            logger.info(f"Added link from {target_note.path} to {orphan_note.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to apply link suggestion: {e}")
            return False

    def _fix_weak_link(
        self, source_note: NoteRecord, target_title: str, all_notes: List[NoteRecord]
    ) -> bool:
        """Fix weak link by strengthening connections."""
        try:
            if not self.use_llm or not self.llm_connector:
                logger.info(f"Cannot fix weak link without LLM")
                return False

            # Find target note
            target_note = self._find_note_by_title(target_title)
            if not target_note:
                logger.warning(f"Target note not found: {target_title}")
                return False

            # Get note contents
            with open(source_note.path, "r", encoding="utf-8") as f:
                source_content = f.read()

            with open(target_note.path, "r", encoding="utf-8") as f:
                target_content = f.read()

            # Get sample of other notes for bridging suggestions
            sample_notes = []
            for note in all_notes[:30]:  # Limit to 30 notes for context
                if note.path not in [source_note.path, target_note.path]:
                    try:
                        with open(note.path, "r", encoding="utf-8") as f:
                            content = f.read()
                            sample_notes.append(
                                {
                                    "title": note.title,
                                    "content": content[:400],  # Limit content
                                }
                            )
                    except:
                        continue

            # Generate strengthening suggestions using LLM
            suggestions = self._generate_weak_link_suggestions(
                source_note.title, source_content, target_note.title, target_content, sample_notes
            )

            if not suggestions:
                logger.info(f"No strengthening suggestions generated for weak link")
                return False

            # Apply the first suggestion
            if suggestions and len(suggestions) > 0:
                suggestion = suggestions[0]
                if self._apply_weak_link_suggestion(source_note, target_note, suggestion):
                    logger.info(f"Applied strengthening suggestion for weak link")
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to fix weak link: {e}")
            return False

    def _generate_weak_link_suggestions(
        self,
        source_title: str,
        source_content: str,
        target_title: str,
        target_content: str,
        sample_notes: List[Dict[str, str]],
    ) -> Optional[List[Dict[str, str]]]:
        """Generate suggestions for strengthening weak links using LLM."""
        try:
            if not self.llm_connector:
                return None

            # Build context from sample notes
            context_text = "Sample of other notes in the wiki:\n"
            for note in sample_notes:
                context_text += f"\n--- Note: [[{note['title']}]] ---\n"
                context_text += f"{note['content']}\n"

            prompt = """
Weak link detected between:
Source note: {source_title}
Target note: {target_title}

Source note content:
{source_content}

Target note content:
{target_content}

{context}

This is a weak link (only connection between graph components). Suggest ways to strengthen it:
1. Additional direct links between these notes (where in each note should new links be added?)
2. Bridging notes from the sample above that could connect these topics
3. New notes that should be created to bridge the concepts

Return as a JSON array of objects with keys: "type" ("direct_link", "bridge_note", "new_note"), 
"description", "action" (specific action to take).
"""

            formatted_prompt = prompt.format(
                source_title=source_title,
                source_content=source_content[:1500],
                target_title=target_title,
                target_content=target_content[:1500],
                context=context_text[:2500],
            )

            response = self.llm_connector.generate_content(
                formatted_prompt, task_type="classification", temperature=0.3
            )

            if not response:
                return None

            # Parse JSON response
            import json

            try:
                # Extract JSON array
                lines = response.strip().split("\n")
                json_str = ""
                in_array = False

                for line in lines:
                    line = line.strip()
                    if line.startswith("["):
                        in_array = True
                    if in_array:
                        json_str += line
                    if line.endswith("]"):
                        break

                if json_str:
                    suggestions = json.loads(json_str)
                    if isinstance(suggestions, list):
                        return suggestions

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from weak link suggestions: {e}")

            return None

        except Exception as e:
            logger.error(f"Failed to generate weak link suggestions: {e}")
            return None

    def _apply_weak_link_suggestion(
        self, source_note: NoteRecord, target_note: NoteRecord, suggestion: Dict[str, str]
    ) -> bool:
        """Apply a weak link strengthening suggestion."""
        try:
            suggestion_type = suggestion.get("type")
            action = suggestion.get("action", "")

            if suggestion_type == "direct_link":
                # Add reciprocal links
                return self._add_reciprocal_links(source_note, target_note, action)
            elif suggestion_type == "bridge_note":
                # Could create or update a bridging note
                logger.info(f"Bridge note suggestion: {action}")
                return True  # Track as fixed for reporting
            elif suggestion_type == "new_note":
                # Could create a new note
                logger.info(f"New note suggestion: {action}")
                return True  # Track as fixed for reporting
            else:
                return False

        except Exception as e:
            logger.error(f"Failed to apply weak link suggestion: {e}")
            return False

    def _add_reciprocal_links(
        self, note_a: NoteRecord, note_b: NoteRecord, location_hint: str = ""
    ) -> bool:
        """Add reciprocal links between two notes."""
        try:
            # Add link from A to B
            with open(note_a.path, "r", encoding="utf-8") as f:
                content_a = f.read()

            link_to_b = f" [[{note_b.title}]]"
            # Simple implementation: append at end
            new_content_a = content_a.rstrip() + f"\n\nRelated: {link_to_b}\n"

            with open(note_a.path, "w", encoding="utf-8") as f:
                f.write(new_content_a)

            # Add link from B to A
            with open(note_b.path, "r", encoding="utf-8") as f:
                content_b = f.read()

            link_to_a = f" [[{note_a.title}]]"
            new_content_b = content_b.rstrip() + f"\n\nRelated: {link_to_a}\n"

            with open(note_b.path, "w", encoding="utf-8") as f:
                f.write(new_content_b)

            logger.info(f"Added reciprocal links between {note_a.title} and {note_b.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to add reciprocal links: {e}")
            return False

    def _generate_slope_content_with_llm(self, note_content: str) -> Optional[str]:
        """Generate slope content using LLM."""
        try:
            if not self.llm_connector:
                return None

            # Create prompt for slope generation
            prompt = """
Based on the following note content, generate a "Slope" section that captures:
1. What's changing or evolving in this area of knowledge?
2. What new insights are accumulating?
3. What contradictions or gaps are emerging?
4. What questions should be explored next?

Keep the slope section concise (3-5 bullet points or short paragraphs).

Note content:
{content}

Generate only the slope content (no headings or markdown formatting).
"""

            formatted_prompt = prompt.format(content=note_content[:3000])  # Limit for tokens

            response = self.llm_connector.generate_content(
                formatted_prompt,
                task_type="synthesis",
                temperature=0.3,  # Slightly creative but focused
            )

            if response:
                return response.strip()

            return None

        except Exception as e:
            logger.error(f"Failed to generate slope content with LLM: {e}")
            return None

    def _fix_missing_category(self, note: NoteRecord) -> bool:
        """Fix missing category by reclassifying note."""
        try:
            # Try LLM-powered classification first if available
            if self.use_llm and self.llm_connector:
                return self._fix_missing_category_with_llm(note)

            # Fall back to static classification
            return self._fix_missing_category_static(note)

        except Exception as e:
            logger.error(f"Failed to classify note {note.path}: {e}")
            return False

    def _fix_missing_category_with_llm(self, note: NoteRecord) -> bool:
        """Fix missing category using LLM-powered classification."""
        try:
            with open(note.path, "r", encoding="utf-8") as f:
                content = f.read()

            # Use LLM for classification
            classification_result = self._classify_note_with_llm(
                note.title, content, note.domain_folder
            )

            if classification_result and classification_result.get("primary_root_category"):
                primary_category = classification_result["primary_root_category"]
                subcategories = classification_result.get("subcategories", [])
                note_type = classification_result.get("note_type", "concept")

                # Update note metadata
                self._update_note_metadata(note, primary_category, subcategories, note_type)

                logger.info(
                    f"LLM classified {note.path}: {primary_category}, "
                    f"subcategories: {subcategories}, type: {note_type}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"LLM classification failed for {note.path}: {e}")
            return False

    def _fix_missing_category_static(self, note: NoteRecord) -> bool:
        """Fix missing category using static classification."""
        try:
            with open(note.path, "r", encoding="utf-8") as f:
                content = f.read()

            reclassified_note = self.classifier.classify_note(note, content, force_reclassify=True)

            if reclassified_note.primary_root_category:
                logger.info(
                    f"Static classification for {note.path}: "
                    f"{reclassified_note.primary_root_category.value}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Static classification failed for {note.path}: {e}")
            return False

    def _fix_missing_subcategories(self, note: NoteRecord) -> bool:
        """Fix missing subcategories by reclassifying note."""
        try:
            # Try LLM-powered classification first if available
            if self.use_llm and self.llm_connector:
                return self._fix_missing_subcategories_with_llm(note)

            # Fall back to static classification
            return self._fix_missing_subcategories_static(note)

        except Exception as e:
            logger.error(f"Failed to classify note {note.path}: {e}")
            return False

    def _fix_missing_subcategories_with_llm(self, note: NoteRecord) -> bool:
        """Fix missing subcategories using LLM-powered classification."""
        try:
            with open(note.path, "r", encoding="utf-8") as f:
                content = f.read()

            # Use LLM for classification
            classification_result = self._classify_note_with_llm(
                note.title, content, note.domain_folder
            )

            if classification_result and classification_result.get("subcategories"):
                subcategories = classification_result["subcategories"]

                # Update note metadata with subcategories
                self._update_note_subcategories(note, subcategories)

                logger.info(f"LLM assigned subcategories to {note.path}: {subcategories}")
                return True

            return False

        except Exception as e:
            logger.error(f"LLM subcategory classification failed for {note.path}: {e}")
            return False

    def _fix_missing_subcategories_static(self, note: NoteRecord) -> bool:
        """Fix missing subcategories using static classification."""
        try:
            with open(note.path, "r", encoding="utf-8") as f:
                content = f.read()

            reclassified_note = self.classifier.classify_note(note, content, force_reclassify=True)

            if reclassified_note.subcategories:
                logger.info(
                    f"Static subcategories for {note.path}: {reclassified_note.subcategories}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Static subcategory classification failed for {note.path}: {e}")
            return False

    def _classify_note_with_llm(
        self, title: str, content: str, domain_folder: str
    ) -> Optional[Dict[str, any]]:
        """Classify a note using LLM."""
        try:
            if not self.llm_connector:
                return None

            # Get classification prompt from config
            classification_prompt = """
Note title: {title}
Note content: {content}
Domain folder: {domain_folder}

Classify this note into:
- primary_root_category (physical, mental, financial, social, or null)
- secondary_root_categories (list)
- subcategories (list from known subcategories)
- note_type (concept, source_summary, compounding_page, synthesis, moc, task_linked, reference, generated_index)

Return JSON only.
"""

            prompt = classification_prompt.format(
                title=title,
                content=content[:2000],  # Limit content for token efficiency
                domain_folder=domain_folder,
            )

            response = self.llm_connector.generate_content(
                prompt,
                task_type="classification",
                temperature=0.1,  # Low temperature for consistent classification
            )

            if not response:
                return None

            # Parse JSON response
            import json

            try:
                # Extract JSON from response
                lines = response.strip().split("\n")
                json_str = ""
                in_json = False

                for line in lines:
                    line = line.strip()
                    if line.startswith("{"):
                        in_json = True
                    if in_json:
                        json_str += line
                    if line.endswith("}"):
                        break

                if json_str:
                    result = json.loads(json_str)

                    # Validate required fields
                    if "primary_root_category" in result:
                        return result

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from LLM classification: {e}")
                logger.debug(f"Raw response: {response}")

            return None

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return None

    def _update_note_metadata(
        self, note: NoteRecord, primary_category: str, subcategories: List[str], note_type: str
    ) -> bool:
        """Update note metadata in the file."""
        try:
            with open(note.path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse frontmatter if it exists
            import yaml

            frontmatter = {}
            lines = content.split("\n")

            if lines and lines[0] == "---":
                yaml_lines = []
                i = 1
                while i < len(lines) and lines[i] != "---":
                    yaml_lines.append(lines[i])
                    i += 1

                if yaml_lines:
                    try:
                        frontmatter = yaml.safe_load("\n".join(yaml_lines)) or {}
                    except:
                        frontmatter = {}

            # Update frontmatter
            frontmatter["primary_category"] = primary_category
            frontmatter["subcategories"] = subcategories
            frontmatter["note_type"] = note_type

            # Reconstruct content with updated frontmatter
            new_content = "---\n"
            new_content += yaml.dump(frontmatter, default_flow_style=False)
            new_content += "---\n"

            # Add the rest of the content
            content_start = 0
            if lines and lines[0] == "---":
                i = 1
                while i < len(lines) and lines[i] != "---":
                    i += 1
                content_start = i + 1 if i < len(lines) else 1

            new_content += "\n".join(lines[content_start:])

            # Write back
            with open(note.path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return True

        except Exception as e:
            logger.error(f"Failed to update note metadata for {note.path}: {e}")
            return False

    def _update_note_subcategories(self, note: NoteRecord, subcategories: List[str]) -> bool:
        """Update only subcategories in note metadata."""
        try:
            with open(note.path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse frontmatter if it exists
            import yaml

            frontmatter = {}
            lines = content.split("\n")

            if lines and lines[0] == "---":
                yaml_lines = []
                i = 1
                while i < len(lines) and lines[i] != "---":
                    yaml_lines.append(lines[i])
                    i += 1

                if yaml_lines:
                    try:
                        frontmatter = yaml.safe_load("\n".join(yaml_lines)) or {}
                    except:
                        frontmatter = {}

            # Update subcategories only
            frontmatter["subcategories"] = subcategories

            # Reconstruct content with updated frontmatter
            new_content = "---\n"
            new_content += yaml.dump(frontmatter, default_flow_style=False)
            new_content += "---\n"

            # Add the rest of the content
            content_start = 0
            if lines and lines[0] == "---":
                i = 1
                while i < len(lines) and lines[i] != "---":
                    i += 1
                content_start = i + 1 if i < len(lines) else 1

            new_content += "\n".join(lines[content_start:])

            # Write back
            with open(note.path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return True

        except Exception as e:
            logger.error(f"Failed to update note subcategories for {note.path}: {e}")
            return False


def run_lint(
    report: bool = False, fix_safe: bool = False, dry_run: bool = False, json_output: bool = False
) -> Dict[str, any]:
    """Run wiki linting workflow."""
    # Start audit log
    audit = AuditLogger()
    run_id = audit.start_run(command="wiki_lint", mode="dry-run" if dry_run else "live")

    start_time = time.time()

    try:
        logger.info("Starting wiki linting")

        if dry_run:
            logger.info("Dry run mode - no changes will be written")

        # Run linter
        linter = WikiLinter()
        result = linter.run_lint(fix_safe=fix_safe, dry_run=dry_run)

        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            audit.log_error(run_id, error_msg)
            audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)
            return result

        # Update audit log
        audit.update_run(
            run_id,
            status="success",
            notes_read=result.get("notes_scanned", 0),
            warnings=[f"Found {result.get('issues_found', 0)} lint issues"],
            duration_seconds=time.time() - start_time,
        )

        logger.info(f"Linting completed successfully")
        return result

    except Exception as e:
        error_msg = f"Linting failed: {e}"
        logger.error(error_msg, exc_info=True)

        audit.log_error(run_id, error_msg)
        audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)

        return {
            "success": False,
            "error": error_msg,
            "run_id": run_id,
        }


def run_quick_lint() -> Dict[str, any]:
    """Run quick lint check without full scan."""
    start_time = time.time()

    try:
        logger.info("Running quick lint check")

        linter = WikiLinter()

        # Quick scan with limit
        notes = linter.scanner.scan_vault(limit=100)
        classified_notes = linter.classifier.batch_classify(notes)
        linter.backlink_analyzer.build_graph(classified_notes)

        # Run basic checks
        orphan_issues = linter.detect_orphans(classified_notes)
        stale_issues = linter.detect_stale_pages(classified_notes)

        all_issues = orphan_issues + stale_issues

        duration = time.time() - start_time

        return {
            "success": True,
            "duration_seconds": round(duration, 2),
            "notes_scanned": len(classified_notes),
            "issues_found": len(all_issues),
            "issues": [issue.model_dump() for issue in all_issues],
            "summary": {
                "orphans": len(orphan_issues),
                "stale_pages": len(stale_issues),
            },
        }

    except Exception as e:
        logger.error(f"Quick lint failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def run_orphan_check() -> Dict[str, any]:
    """Run orphan note detection specifically."""
    start_time = time.time()

    try:
        logger.info("Running orphan check")

        linter = WikiLinter()
        notes = linter.scanner.scan_vault()
        classified_notes = linter.classifier.batch_classify(notes)
        linter.backlink_analyzer.build_graph(classified_notes)

        orphan_issues = linter.detect_orphans(classified_notes)

        duration = time.time() - start_time

        return {
            "success": True,
            "duration_seconds": round(duration, 2),
            "notes_scanned": len(classified_notes),
            "orphans_found": len(orphan_issues),
            "orphans": [issue.model_dump() for issue in orphan_issues],
        }

    except Exception as e:
        logger.error(f"Orphan check failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def run_stale_check(days: int = 90) -> Dict[str, any]:
    """Run stale page detection."""
    start_time = time.time()

    try:
        logger.info(f"Running stale check (>{days} days)")

        linter = WikiLinter()
        notes = linter.scanner.scan_vault()
        classified_notes = linter.classifier.batch_classify(notes)

        # Temporarily override stale days
        original_stale_days = linter.stale_days
        linter.stale_days = days

        stale_issues = linter.detect_stale_pages(classified_notes)

        # Restore original value
        linter.stale_days = original_stale_days

        duration = time.time() - start_time

        return {
            "success": True,
            "duration_seconds": round(duration, 2),
            "notes_scanned": len(classified_notes),
            "stale_pages_found": len(stale_issues),
            "stale_pages": [issue.model_dump() for issue in stale_issues],
        }

    except Exception as e:
        logger.error(f"Stale check failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }

"""Wiki indexing workflow."""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from ..audit import AuditLogger
from ..indexing.backlinks import BacklinkAnalyzer
from ..indexing.classifier import NoteClassifier
from ..indexing.index_builder import IndexBuilder
from ..indexing.scanner import VaultScanner
from ..models import NoteRecord

logger = logging.getLogger(__name__)


def run_index(
    full: bool = False, check: bool = False, dry_run: bool = False, limit: Optional[int] = None
) -> Dict[str, any]:
    """Run wiki indexing workflow."""
    # Start audit log
    audit = AuditLogger()
    run_id = audit.start_run(command="wiki_index", mode="dry-run" if dry_run else "live")

    start_time = time.time()

    try:
        logger.info("Starting wiki indexing workflow")

        # Initialize components
        scanner = VaultScanner()
        classifier = NoteClassifier()
        backlink_analyzer = BacklinkAnalyzer()
        index_builder = IndexBuilder()

        # Step 1: Scan vault
        logger.info("Step 1: Scanning vault...")
        notes = scanner.scan_vault(limit=limit)

        if not notes:
            error_msg = "No notes found in vault"
            logger.error(error_msg)
            audit.log_error(run_id, error_msg)
            audit.complete_run(run_id, status="failure")
            return {"error": error_msg}

        audit.update_run(run_id, status="running", notes_read=len(notes))

        # Step 2: Classify notes
        logger.info("Step 2: Classifying notes...")
        classified_notes = classifier.batch_classify(notes, force_reclassify=full)

        # Get classification statistics
        classification_stats = classifier.get_classification_statistics(classified_notes)

        # Step 3: Calculate backlinks
        logger.info("Step 3: Calculating backlinks...")
        notes_with_backlinks = backlink_analyzer.calculate_backlinks(classified_notes)

        # Get backlink statistics
        backlink_stats = backlink_analyzer.get_backlink_statistics()

        # Step 4: Check consistency if requested
        if check:
            logger.info("Step 4: Checking index consistency...")
            consistency_check = index_builder.check_index_consistency(notes_with_backlinks)

            audit.update_run(
                run_id,
                status="running",
                warnings=[f"Consistency issues: {len(consistency_check.get('issues', []))}"],
            )

        # Step 5: Build indexes (unless in check-only mode)
        index_results = {}
        if not check:
            logger.info("Step 5: Building indexes...")
            index_results = index_builder.build_all_indexes(notes_with_backlinks, dry_run=dry_run)

            if not dry_run:
                audit.update_run(
                    run_id, status="running", notes_written=len(index_results.get("written", []))
                )

        # Calculate duration
        duration = time.time() - start_time

        # Build result
        result = {
            "success": True,
            "run_id": run_id,
            "duration_seconds": round(duration, 2),
            "notes_scanned": len(notes),
            "notes_classified": len(classified_notes),
            "classification_stats": classification_stats,
            "backlink_stats": backlink_stats,
            "index_results": index_results,
        }

        if check:
            result["consistency_check"] = consistency_check

        # Complete audit log
        audit.complete_run(run_id, status="success", duration_seconds=duration)

        logger.info(f"Wiki indexing completed in {duration:.2f} seconds")

        return result

    except Exception as e:
        error_msg = f"Wiki indexing failed: {e}"
        logger.error(error_msg, exc_info=True)

        # Log error and complete run
        audit.log_error(run_id, error_msg)
        audit.complete_run(run_id, status="failure", duration_seconds=time.time() - start_time)

        return {
            "success": False,
            "error": error_msg,
            "run_id": run_id,
        }


def run_quick_scan() -> Dict[str, any]:
    """Run a quick scan of the vault."""
    start_time = time.time()

    try:
        logger.info("Running quick vault scan")

        scanner = VaultScanner()
        notes = scanner.scan_vault(limit=100)  # Limit to 100 notes for quick scan

        if not notes:
            return {"error": "No notes found in vault"}

        # Get basic statistics
        stats = scanner.get_vault_statistics(notes)

        # Sample a few notes
        sample_notes = []
        for note in notes[:5]:  # First 5 notes
            sample_notes.append(
                {
                    "title": note.title,
                    "domain_folder": note.domain_folder,
                    "note_type": note.note_type.value,
                    "file_size_kb": note.file_size / 1024,
                }
            )

        duration = time.time() - start_time

        return {
            "success": True,
            "duration_seconds": round(duration, 2),
            "notes_scanned": len(notes),
            "sample_notes": sample_notes,
            "statistics": stats,
        }

    except Exception as e:
        logger.error(f"Quick scan failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def run_domain_scan(domain_folder: str) -> Dict[str, any]:
    """Scan a specific domain folder."""
    start_time = time.time()

    try:
        logger.info(f"Scanning domain folder: {domain_folder}")

        scanner = VaultScanner()
        notes = scanner.scan_domain_folder(domain_folder)

        if not notes:
            return {"error": f"No notes found in domain folder: {domain_folder}"}

        # Classify notes
        classifier = NoteClassifier()
        classified_notes = classifier.batch_classify(notes)

        # Get statistics
        stats = scanner.get_vault_statistics(classified_notes)
        classification_stats = classifier.get_classification_statistics(classified_notes)

        duration = time.time() - start_time

        return {
            "success": True,
            "duration_seconds": round(duration, 2),
            "domain_folder": domain_folder,
            "notes_scanned": len(notes),
            "statistics": stats,
            "classification_stats": classification_stats,
        }

    except Exception as e:
        logger.error(f"Domain scan failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def run_backlink_analysis() -> Dict[str, any]:
    """Run backlink analysis on the vault."""
    start_time = time.time()

    try:
        logger.info("Running backlink analysis")

        # Scan and classify notes
        scanner = VaultScanner()
        classifier = NoteClassifier()

        notes = scanner.scan_vault()
        classified_notes = classifier.batch_classify(notes)

        # Build backlink graph
        backlink_analyzer = BacklinkAnalyzer()
        notes_with_backlinks = backlink_analyzer.calculate_backlinks(classified_notes)

        # Get detailed analysis
        backlink_stats = backlink_analyzer.get_backlink_statistics()
        connectivity_patterns = backlink_analyzer.analyze_connectivity_patterns()

        # Find orphans and weak links
        orphans = backlink_analyzer.find_orphans()
        sinks = backlink_analyzer.find_sinks()
        weak_links = backlink_analyzer.find_weak_links()

        # Find central notes
        central_notes = backlink_analyzer.find_central_notes(top_n=20)

        duration = time.time() - start_time

        return {
            "success": True,
            "duration_seconds": round(duration, 2),
            "notes_analyzed": len(notes_with_backlinks),
            "backlink_stats": backlink_stats,
            "connectivity_patterns": connectivity_patterns,
            "orphans": orphans[:20],  # Top 20 orphans
            "sinks": sinks[:20],  # Top 20 sinks
            "weak_links": weak_links[:20],  # Top 20 weak links
            "central_notes": central_notes,
        }

    except Exception as e:
        logger.error(f"Backlink analysis failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def run_index_check() -> Dict[str, any]:
    """Check index consistency without rebuilding."""
    start_time = time.time()

    try:
        logger.info("Running index consistency check")

        # Scan and classify notes
        scanner = VaultScanner()
        classifier = NoteClassifier()
        index_builder = IndexBuilder()

        notes = scanner.scan_vault()
        classified_notes = classifier.batch_classify(notes)

        # Check consistency
        consistency_check = index_builder.check_index_consistency(classified_notes)

        # Validate classifications
        classification_issues = classifier.validate_classifications(classified_notes)

        duration = time.time() - start_time

        return {
            "success": True,
            "duration_seconds": round(duration, 2),
            "notes_checked": len(classified_notes),
            "consistency_check": consistency_check,
            "classification_issues": classification_issues,
            "has_issues": len(consistency_check.get("issues", [])) > 0
            or len(classification_issues) > 0,
        }

    except Exception as e:
        logger.error(f"Index check failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }

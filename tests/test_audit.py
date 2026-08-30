"""Tests for the AuditLogger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veltiosi.audit import AuditLogger


@pytest.fixture
def audit(audit_dir):
    return AuditLogger(audit_dir=audit_dir)


class TestAuditLoggerInit:
    def test_directories_created(self, audit_dir):
        al = AuditLogger(audit_dir=audit_dir)
        assert al.events_dir.exists()
        assert al.review_queue_dir.exists()
        assert al.reports_dir.exists()


class TestAuditRunLifecycle:
    def test_start_run_returns_string_id(self, audit):
        run_id = audit.start_run(command="test_cmd", mode="dry-run")
        assert isinstance(run_id, str)
        assert len(run_id) > 0

    def test_start_run_creates_event_file(self, audit):
        run_id = audit.start_run("wiki_index", "live")
        event_file = audit.events_dir / f"{run_id}.json"
        assert event_file.exists()

    def test_event_file_is_valid_json(self, audit):
        run_id = audit.start_run("wiki_lint", "dry-run")
        event_file = audit.events_dir / f"{run_id}.json"
        with open(event_file) as f:
            data = json.load(f)
        assert data["run_id"] == run_id
        assert data["command"] == "wiki_lint"

    def test_complete_run_updates_status(self, audit):
        run_id = audit.start_run("cmd", "live")
        audit.complete_run(run_id, status="success")
        event_file = audit.events_dir / f"{run_id}.json"
        with open(event_file) as f:
            data = json.load(f)
        assert data["status"] == "success"

    def test_update_run_sets_notes_read(self, audit):
        run_id = audit.start_run("cmd", "live")
        audit.update_run(run_id, status="running", notes_read=42)
        with open(audit.events_dir / f"{run_id}.json") as f:
            data = json.load(f)
        assert data["notes_read"] == 42

    def test_log_error_appends_to_errors_list(self, audit):
        run_id = audit.start_run("cmd", "live")
        audit.log_error(run_id, "Something went wrong")
        with open(audit.events_dir / f"{run_id}.json") as f:
            data = json.load(f)
        assert len(data["errors"]) == 1
        assert "Something went wrong" in data["errors"][0]

    def test_log_warning_appends_to_warnings_list(self, audit):
        run_id = audit.start_run("cmd", "live")
        audit.log_warning(run_id, "Careful!")
        with open(audit.events_dir / f"{run_id}.json") as f:
            data = json.load(f)
        assert len(data["warnings"]) == 1

    def test_multiple_errors_accumulate(self, audit):
        run_id = audit.start_run("cmd", "live")
        audit.log_error(run_id, "Error 1")
        audit.log_error(run_id, "Error 2")
        with open(audit.events_dir / f"{run_id}.json") as f:
            data = json.load(f)
        assert len(data["errors"]) == 2


class TestAuditReviewQueue:
    def test_add_to_review_queue_returns_queue_id(self, audit):
        qid = audit.add_to_review_queue(
            task_id=1,
            task_title="Fix something",
            ambiguity_reason="Low confidence",
            proposed_mappings=[{"category": "mental"}],
            candidate_pages=["Page A", "Page B"],
        )
        assert qid is not None
        assert isinstance(qid, str)

    def test_review_item_file_created(self, audit):
        qid = audit.add_to_review_queue(
            task_id=2,
            task_title="T",
            ambiguity_reason="R",
            proposed_mappings=[],
            candidate_pages=[],
        )
        assert (audit.review_queue_dir / f"{qid}.json").exists()

    def test_get_review_queue_returns_pending_items(self, audit):
        audit.add_to_review_queue(
            task_id=10,
            task_title="My Task",
            ambiguity_reason="Unclear",
            proposed_mappings=[],
            candidate_pages=[],
        )
        items = audit.get_review_queue(status="pending")
        assert len(items) >= 1

    def test_update_review_item_changes_status(self, audit):
        qid = audit.add_to_review_queue(
            task_id=3,
            task_title="T",
            ambiguity_reason="R",
            proposed_mappings=[],
            candidate_pages=[],
        )
        audit.update_review_item(qid, status="resolved", resolution_notes="Done")
        resolved = audit.get_review_queue(status="resolved")
        assert any(i.queue_id == qid for i in resolved)


class TestAuditStats:
    def test_get_stats_returns_dict(self, audit):
        stats = audit.get_stats()
        assert isinstance(stats, dict)
        assert "total_events" in stats
        assert "disk_usage_mb" in stats

    def test_stats_reflect_created_runs(self, audit):
        audit.start_run("a", "live")
        audit.start_run("b", "dry-run")
        stats = audit.get_stats()
        assert stats["total_events"] >= 2


class TestAuditReport:
    def test_generate_report_returns_dict(self, audit):
        run_id = audit.start_run("wiki_index", "live")
        audit.complete_run(run_id, status="success")
        report = audit.generate_report()
        assert isinstance(report, dict)
        assert "summary" in report
        assert "events" in report
        assert "review_queue_stats" in report

    def test_report_counts_match_runs(self, audit):
        for i in range(3):
            rid = audit.start_run("cmd", "live")
            audit.complete_run(rid, status="success")
        report = audit.generate_report()
        assert report["summary"]["total_runs"] >= 3
        assert report["summary"]["successful_runs"] >= 3

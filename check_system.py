#!/usr/bin/env python3
"""Comprehensive system check for Veltiosi."""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'=' * 60}")
    print(f"Testing: {description}")
    print(f"Command: {cmd}")
    print(f"{'=' * 60}")

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=Path.home() / "veltiosi",
        )

        if result.returncode == 0:
            print(f"✓ SUCCESS")
            if result.stdout.strip():
                print(f"Output:\n{result.stdout[:500]}...")
            return True
        else:
            print(f"✗ FAILED (exit code: {result.returncode})")
            if result.stderr:
                print(f"Error:\n{result.stderr[:500]}")
            return False

    except Exception as e:
        print(f"✗ EXCEPTION: {e}")
        return False


def main():
    """Run comprehensive system checks."""
    print("Veltiosi System Check")
    print("=" * 60)

    tests = [
        # Basic CLI tests
        ("veltiosi status", "Basic system status"),
        ("veltiosi config-show", "Configuration display"),
        # Workflow tests (dry-run)
        ("veltiosi wiki-index --check", "Index consistency check"),
        ("veltiosi wiki-lint --dry-run", "Lint check (dry run)"),
        # New workflow tests
        ("veltiosi wiki-query 'test query' --dry-run", "Wiki query (dry run)"),
        (
            "echo 'test content' > /tmp/test_source.txt && veltiosi wiki-ingest /tmp/test_source.txt --dry-run",
            "Source ingest (dry run)",
        ),
        ("veltiosi weekly-synthesis --dry-run", "Weekly synthesis (dry run)"),
        # Hermes integration
        ("veltiosi hermes-status", "Hermes integration status"),
    ]

    passed = 0
    total = len(tests)

    for cmd, description in tests:
        if run_command(cmd, description):
            passed += 1

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {passed}/{total} tests passed")

    if passed == total:
        print("✓ All tests passed! Veltiosi is ready to use.")
        print("\nNext steps:")
        print("1. Set up Google Gemini API key in .env file for LLM features")
        print("2. Run 'veltiosi hermes-setup' to complete Hermes integration")
        print("3. Try actual workflows (remove --dry-run flag)")
        print("4. Use 'hermes veltiosi <command>' to run through Hermes")
        return 0
    else:
        print(f"⚠ {total - passed} tests failed")
        print("\nTroubleshooting:")
        print("1. Check that .env file exists with correct paths")
        print("2. Make sure Obsidian vault exists at configured location")
        print("3. Run 'pip install -e .' to ensure package is installed")
        print("4. Check Python path and dependencies")
        return 1


if __name__ == "__main__":
    sys.exit(main())

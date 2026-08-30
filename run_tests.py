#!/usr/bin/env python3
"""Run Veltiosi test suite."""

import sys
import subprocess
import argparse


def run_pytest(verbose: bool = False, coverage: bool = False):
    """Run pytest with specified options."""
    cmd = ["pytest", "tests/"]

    if verbose:
        cmd.append("-v")

    if coverage:
        cmd.extend(["--cov=src.veltiosi", "--cov-report=term-missing"])

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def run_specific_test(test_path: str, verbose: bool = False):
    """Run a specific test file."""
    cmd = ["pytest", test_path]

    if verbose:
        cmd.append("-v")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run Veltiosi tests")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage report",
    )
    parser.add_argument(
        "--test",
        help="Run specific test file (e.g., tests/test_services.py)",
    )

    args = parser.parse_args()

    if args.test:
        return_code = run_specific_test(args.test, args.verbose)
    else:
        return_code = run_pytest(args.verbose, args.coverage)

    sys.exit(return_code)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Convenience launcher for all six SpiderSQL DB50/DB51 test suites."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPTS = {
    "db50": [
        "run_adventureworks_100_normal_db50.py",
        "run_adventureworks_100_structured_db50.py",
        "run_adventureworks_containment_30_db50.py",
    ],
    "db51": [
        "run_tpcds_100_normal_db51.py",
        "run_tpcds_100_structured_db51.py",
        "run_tpcds_containment_30_db51.py",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", choices=["db50", "db51", "all"], default="all")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--sleep", type=float, default=0.2)
    args = parser.parse_args()

    selected = []
    if args.database in ("db50", "all"):
        selected.extend(SCRIPTS["db50"])
    if args.database in ("db51", "all"):
        selected.extend(SCRIPTS["db51"])

    backend = Path.cwd()
    failures = 0
    for script in selected:
        command = [
            sys.executable,
            str(backend / script),
            "--base-url",
            args.base_url,
            "--timeout",
            str(args.timeout),
            "--sleep",
            str(args.sleep),
        ]
        print("=" * 108)
        print("RUNNING:", " ".join(command))
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            failures += 1
            print(f"SUITE FAILED: {script} (exit {completed.returncode})")
        else:
            print(f"SUITE PASSED: {script}")

    print("=" * 108)
    print(f"Completed {len(selected)} suite(s); failures: {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

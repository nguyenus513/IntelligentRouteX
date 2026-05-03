from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase8-v1"


def run_command(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, check=False)
    return int(completed.returncode)


def certification_command(suite: str, solver: str, output_root: Path, time_limit: str, data_source: str) -> list[str]:
    return [
        sys.executable,
        "scripts/run_external_benchmark_certification.py",
        "--suite",
        suite,
        "--preset",
        "preset:smoke",
        "--solver",
        solver,
        "--data-source",
        data_source,
        "--time-limit",
        time_limit,
        "--output-root",
        str(output_root / solver / suite),
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 8 community benchmark smoke certification.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="fixture")
    parser.add_argument("--include-ortools", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_root = Path(args.output_dir)
    solvers = ["our-dispatch-v2"]
    if args.include_ortools:
        solvers.append("ortools-baseline")
    commands = [
        certification_command(suite, solver, output_root, args.time_limit, args.data_source)
        for solver in solvers
        for suite in ("solomon", "li-lim")
    ]
    print(f"[COMMUNITY PHASE8] planned {len(commands)} certification run(s)")
    for command in commands:
        print("- " + " ".join(command))
    if args.dry_run:
        return 0

    failures: list[str] = []
    for command in commands:
        code = run_command(command)
        if code != 0:
            failures.append(" ".join(command))
    if failures:
        print("[COMMUNITY PHASE8] failures:")
        for failure in failures:
            print("- " + failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

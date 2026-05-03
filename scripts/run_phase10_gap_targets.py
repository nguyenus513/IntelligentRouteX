from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase10-gap-targets-v1"
TARGETS = {
    "solomon": "RC101",
    "li-lim": "LR101,LRC101",
}


def run_command(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, check=False)
    return int(completed.returncode)


def certification_command(suite: str, instances: str, output_root: Path, time_limit: str, data_source: str) -> list[str]:
    return [
        sys.executable,
        "scripts/run_external_benchmark_certification.py",
        "--suite",
        suite,
        "--instances",
        instances,
        "--solver",
        "our-dispatch-v2",
        "--data-source",
        data_source,
        "--time-limit",
        time_limit,
        "--output-root",
        str(output_root / "our-dispatch-v2" / suite),
    ]


def planned_commands(output_dir: Path, time_limit: str, data_source: str) -> list[list[str]]:
    return [certification_command(suite, instances, output_dir, time_limit, data_source)
            for suite, instances in TARGETS.items()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 10 vehicle-gap target certification cases.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--time-limit", default="15s")
    parser.add_argument("--data-source", choices=("official", "auto"), default="auto")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    commands = planned_commands(output_dir, args.time_limit, args.data_source)
    print(f"[PHASE10 TARGETS] planned {len(commands)} certification run(s)")
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
        print("[PHASE10 TARGETS] failures:")
        for failure in failures:
            print("- " + failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

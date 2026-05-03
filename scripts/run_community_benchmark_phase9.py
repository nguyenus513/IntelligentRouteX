from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase9-official-smoke-v1"
PRESETS = {
    "official-smoke": {
        "solomon": "C101,R101,RC101",
        "li-lim": "LC101,LR101,LRC101",
    },
    "official-core": {
        "solomon": "C101,C201,R101,R201,RC101,RC201",
        "li-lim": "LC101,LC102,LC103,LR101,LR102,LR103,LRC101,LRC102,LRC103",
    },
}


def run_command(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, check=False)
    return int(completed.returncode)


def certification_command(
    suite: str,
    solver: str,
    instances: str,
    output_root: Path,
    time_limit: str,
    data_source: str,
) -> list[str]:
    return [
        sys.executable,
        "scripts/run_external_benchmark_certification.py",
        "--suite",
        suite,
        "--instances",
        instances,
        "--solver",
        solver,
        "--data-source",
        data_source,
        "--time-limit",
        time_limit,
        "--output-root",
        str(output_root / solver / suite),
    ]


def planned_commands(args: argparse.Namespace) -> list[list[str]]:
    preset = PRESETS[args.preset]
    solvers = ["our-dispatch-v2"]
    if args.include_ortools:
        solvers.append("ortools-baseline")
    if args.include_pyvrp:
        solvers.append("pyvrp-baseline")
    return [
        certification_command(suite, solver, instances, Path(args.output_dir), args.time_limit, args.data_source)
        for solver in solvers
        for suite, instances in preset.items()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 9 official/auto community benchmark certification matrix.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--preset", choices=tuple(PRESETS.keys()), default="official-smoke")
    parser.add_argument("--time-limit", default="15s")
    parser.add_argument("--data-source", choices=("official", "auto"), default="auto")
    parser.add_argument("--include-ortools", action="store_true")
    parser.add_argument("--include-pyvrp", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    commands = planned_commands(args)
    print(f"[COMMUNITY PHASE9] planned {len(commands)} certification run(s)")
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
        print("[COMMUNITY PHASE9] failures:")
        for failure in failures:
            print("- " + failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

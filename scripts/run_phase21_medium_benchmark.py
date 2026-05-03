from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from build_phase15_large_benchmark_report import build_report as build_phase15_report, markdown as report_markdown
from run_external_benchmark_certification import parse_time_limit
from run_phase15_large_benchmark import run_targets

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase21-medium-benchmark-v1"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_phase21(output_dir: Path, time_limit_ms: int, data_source: str, instance_limit: int | None, resume: bool) -> dict[str, Any]:
    phase15_payload = run_targets(
        output_dir=output_dir,
        tier="medium",
        solvers=["our-dispatch-v2", "ortools-baseline"],
        time_limit_ms=time_limit_ms,
        data_source=data_source,
        resume=resume,
        instance_limit=instance_limit,
    )
    aggregate = build_phase15_report(output_dir)
    result = {
        "schemaVersion": "phase21-medium-benchmark-results/v1",
        "timeLimitMs": time_limit_ms,
        "dataSource": data_source,
        "instanceLimit": instance_limit,
        "phase15Payload": phase15_payload,
        "aggregateReport": aggregate,
    }
    write_json(output_dir / "phase21_medium_benchmark_results.json", result)
    write_json(output_dir / "phase21_medium_benchmark_report.json", aggregate)
    (output_dir / "phase21_medium_benchmark_report.md").write_text(markdown(result), encoding="utf-8")
    return result


def markdown(result: dict[str, Any]) -> str:
    aggregate = result["aggregateReport"]
    lines = [
        "# Phase 21 Medium Benchmark Report",
        "",
        f"- completed cells: `{aggregate.get('completedCells')}/{aggregate.get('totalCells')}`",
        f"- wins/ties/losses: `{aggregate.get('wins')}/{aggregate.get('ties')}/{aggregate.get('losses')}`",
        f"- time limit ms: `{result['timeLimitMs']}`",
        f"- data source: `{result['dataSource']}`",
        "",
        "## Aggregate",
        "",
    ]
    lines.extend(report_markdown(aggregate).splitlines()[4:])
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 21 medium whole-system benchmark.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--time-limit", default="5s")
    parser.add_argument("--data-source", choices=("official", "auto", "fixture"), default="auto")
    parser.add_argument("--instance-limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    result = run_phase21(Path(args.output_dir), parse_time_limit(args.time_limit), args.data_source, args.instance_limit or None, args.resume)
    print(f"[PHASE21 MEDIUM BENCHMARK] wrote {args.output_dir}")
    rows = result["phase15Payload"].get("results", [])
    return 1 if any(row.get("verdict") == "FAIL" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from run_phase15_large_benchmark import run_targets
from run_external_benchmark_certification import parse_time_limit

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase16-gap-reduction-v1"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_phase16(output_dir: Path, time_limit_ms: int, data_source: str, instance_limit: int | None) -> dict[str, Any]:
    phase15_payload = run_targets(
        output_dir=output_dir,
        tier="gap",
        solvers=["our-dispatch-v2", "ortools-baseline"],
        time_limit_ms=time_limit_ms,
        data_source=data_source,
        resume=False,
        instance_limit=instance_limit,
    )
    rows = phase15_payload.get("results", [])
    budget_rows = []
    for row in rows:
        if row.get("solver") != "our-dispatch-v2":
            continue
        solution_path = row.get("solutionPath")
        budget_policy: dict[str, Any] = {}
        if solution_path and Path(solution_path).exists():
            solution = json.loads(Path(solution_path).read_text(encoding="utf-8"))
            budget_policy = solution.get("budgetPolicy", {}) if isinstance(solution.get("budgetPolicy"), dict) else {}
        budget_rows.append({
            "suite": row.get("suite"),
            "instance": row.get("instance"),
            "vehicleCount": row.get("vehicleCount"),
            "bestKnownVehicleCount": row.get("bestKnownVehicleCount"),
            "totalDistance": row.get("totalDistance"),
            "runtimeMs": row.get("runtimeMs"),
            "verdict": row.get("verdict"),
            "budgetPolicy": budget_policy,
        })
    result = {
        "schemaVersion": "phase16-gap-reduction-results/v1",
        "strategy": "short-budget-parity-and-gap-target-harness",
        "timeLimitMs": time_limit_ms,
        "dataSource": data_source,
        "phase15Payload": phase15_payload,
        "budgetRows": budget_rows,
    }
    write_json(output_dir / "phase16_gap_reduction_results.json", result)
    (output_dir / "phase16_gap_reduction_report.md").write_text(markdown(result), encoding="utf-8")
    return result


def markdown(result: dict[str, Any]) -> str:
    payload = result["phase15Payload"]
    lines = [
        "# Phase 16 Gap Reduction Results",
        "",
        f"- strategy: `{result['strategy']}`",
        f"- completed cells: `{payload.get('completedCells')}/{payload.get('totalCells')}`",
        f"- time limit ms: `{result['timeLimitMs']}`",
        "",
        "| Suite | Instance | Vehicles | BKS | Distance | Runtime | Budget Mode | Construction | Consolidation | Verdict |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in result["budgetRows"]:
        budget = row.get("budgetPolicy", {})
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('vehicleCount')} | {row.get('bestKnownVehicleCount')} | "
            f"{row.get('totalDistance')} | {row.get('runtimeMs')} | {budget.get('mode')} | "
            f"{budget.get('constructionMs')} | {budget.get('consolidationMs')} | {row.get('verdict')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 16 gap-reduction target benchmark.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--time-limit", default="3s")
    parser.add_argument("--data-source", choices=("official", "auto", "fixture"), default="auto")
    parser.add_argument("--instance-limit", type=int, default=0)
    args = parser.parse_args(argv)
    result = run_phase16(Path(args.output_dir), parse_time_limit(args.time_limit), args.data_source, args.instance_limit or None)
    print(f"[PHASE16 GAP REDUCTION] wrote {args.output_dir}")
    return 1 if any(row.get("verdict") == "FAIL" for row in result["phase15Payload"].get("results", [])) else 0


if __name__ == "__main__":
    raise SystemExit(main())

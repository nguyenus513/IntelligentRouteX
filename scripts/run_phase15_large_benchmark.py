from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Sequence

from run_external_benchmark_certification import run_instance, parse_time_limit

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase15-large-fast-v1"

TIER_TARGETS: dict[str, dict[str, list[str]]] = {
    "fast": {
        "solomon": ["C101", "R101", "RC101"],
        "li-lim": ["LC101", "LR101", "LRC101"],
    },
    "gap": {
        "solomon": ["RC101"],
        "li-lim": ["LR101", "LRC101"],
    },
    "medium": {
        "solomon": ["C101", "C102", "C201", "R101", "R102", "R201", "RC101", "RC102", "RC201"],
        "li-lim": ["LC101", "LC102", "LC103", "LR101", "LR102", "LR103", "LRC101", "LRC102", "LRC103"],
    },
}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def discover_official_instances(suite: str) -> list[str]:
    if suite == "solomon":
        root = REPO_ROOT / "benchmarks" / "external" / "official" / "solomon"
    elif suite == "li-lim":
        root = REPO_ROOT / "benchmarks" / "external" / "official" / "li-lim-pdptw"
    else:
        raise ValueError(f"Unsupported suite: {suite}")
    return sorted(path.stem for path in root.glob("*.txt"))


def target_instances(tier: str, instance_limit: int | None = None) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    if tier == "large":
        for suite in ("solomon", "li-lim"):
            targets.extend((suite, instance) for instance in discover_official_instances(suite))
    else:
        for suite, instances in TIER_TARGETS[tier].items():
            targets.extend((suite, instance) for instance in instances)
    if instance_limit is not None and instance_limit > 0:
        return targets[:instance_limit]
    return targets


def parse_solvers(value: str) -> list[str]:
    solvers = [part.strip() for part in value.split(",") if part.strip()]
    allowed = {"our-dispatch-v2", "ortools-baseline", "pyvrp-baseline"}
    unknown = sorted(set(solvers) - allowed)
    if unknown:
        raise ValueError(f"Unsupported solver(s): {unknown}")
    return solvers


def row_key(row: dict[str, Any]) -> str:
    return f"{row.get('solver')}::{row.get('suite')}::{row.get('instance')}"


def load_existing(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row_key(row): row for row in payload.get("results", [])}


def write_results(output_dir: Path, payload: dict[str, Any]) -> None:
    write_json(output_dir / "phase15_large_benchmark_results.json", payload)


def run_targets(
    output_dir: Path,
    tier: str,
    solvers: Sequence[str],
    time_limit_ms: int,
    data_source: str,
    resume: bool,
    instance_limit: int | None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "phase15_large_benchmark_results.json"
    existing = load_existing(result_path) if resume else {}
    rows = list(existing.values())
    started = time.perf_counter()
    targets = target_instances(tier, instance_limit)
    total_cells = len(targets) * len(solvers)
    completed = len(rows)
    for suite, instance in targets:
        for solver in solvers:
            key = f"{solver}::{suite}::{instance}"
            if key in existing:
                continue
            cell_started = time.perf_counter()
            try:
                row = run_instance(
                    suite=suite,
                    instance=instance,
                    solver=solver,
                    output_root=output_dir / "certification",
                    gap_limit=20.0,
                    time_limit_ms=time_limit_ms,
                    data_source=data_source,
                )
            except Exception as exception:
                row = {
                    "suite": suite,
                    "instance": instance,
                    "solver": solver,
                    "feasible": False,
                    "runtimeMs": int((time.perf_counter() - cell_started) * 1000),
                    "verdict": "FAIL",
                    "verdictReasons": [f"phase15-runner-error:{type(exception).__name__}:{exception}"],
                }
            row["phase15Tier"] = tier
            row["phase15TimeLimitMs"] = time_limit_ms
            row["phase15CellKey"] = key
            rows.append(row)
            completed += 1
            payload = {
                "schemaVersion": "phase15-large-benchmark-results/v1",
                "tier": tier,
                "solvers": list(solvers),
                "dataSource": data_source,
                "timeLimitMs": time_limit_ms,
                "targetCount": len(targets),
                "totalCells": total_cells,
                "completedCells": completed,
                "runtimeMs": int((time.perf_counter() - started) * 1000),
                "results": rows,
            }
            write_results(output_dir, payload)
    payload = {
        "schemaVersion": "phase15-large-benchmark-results/v1",
        "tier": tier,
        "solvers": list(solvers),
        "dataSource": data_source,
        "timeLimitMs": time_limit_ms,
        "targetCount": len(targets),
        "totalCells": total_cells,
        "completedCells": len(rows),
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "results": sorted(rows, key=lambda row: (str(row.get("suite")), str(row.get("instance")), str(row.get("solver")))),
    }
    write_results(output_dir, payload)
    (output_dir / "phase15_large_benchmark_report.md").write_text(markdown(payload), encoding="utf-8")
    return payload


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 15 Large Benchmark Results",
        "",
        f"- tier: `{payload['tier']}`",
        f"- solvers: `{payload['solvers']}`",
        f"- completed cells: `{payload['completedCells']}/{payload['totalCells']}`",
        f"- runtime ms: `{payload['runtimeMs']}`",
        "",
        "| Suite | Instance | Solver | Feasible | Vehicles | BKS | Distance | Runtime | Verdict | Reasons |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in payload["results"]:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('solver')} | {row.get('feasible')} | "
            f"{row.get('vehicleCount')} | {row.get('bestKnownVehicleCount')} | {row.get('totalDistance')} | "
            f"{row.get('runtimeMs')} | {row.get('verdict')} | {row.get('verdictReasons', [])} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 15 resumable large community benchmark.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--tier", choices=("fast", "medium", "large", "gap"), default="fast")
    parser.add_argument("--solvers", default="our-dispatch-v2,ortools-baseline")
    parser.add_argument("--time-limit", default="15s")
    parser.add_argument("--data-source", choices=("official", "auto", "fixture"), default="auto")
    parser.add_argument("--instance-limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    solvers = parse_solvers(args.solvers)
    targets = target_instances(args.tier, args.instance_limit or None)
    print(f"[PHASE15 LARGE BENCHMARK] tier={args.tier} targets={len(targets)} solvers={solvers}")
    if args.dry_run:
        for suite, instance in targets:
            print(f"- {suite}/{instance}")
        return 0
    result = run_targets(Path(args.output_dir), args.tier, solvers, parse_time_limit(args.time_limit), args.data_source, args.resume, args.instance_limit or None)
    print(f"[PHASE15 LARGE BENCHMARK] wrote {args.output_dir}")
    return 1 if any(row.get("verdict") == "FAIL" for row in result["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())

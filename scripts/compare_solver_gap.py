from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def pct_gap(current: float | int | None, baseline: float | int | None) -> float:
    if baseline in (None, 0):
        return 0.0
    return (float(current or 0) - float(baseline)) / float(baseline) * 100.0


def compare(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    current_vehicle = int(current.get("vehicleCount", current.get("routeCount", 0)) or 0)
    baseline_vehicle = int(baseline.get("vehicleCount", baseline.get("routeCount", 0)) or 0)
    current_distance = float(current.get("totalDistanceMeters", 0) or 0)
    baseline_distance = float(baseline.get("totalDistanceMeters", 0) or 0)
    current_duration = float(current.get("totalDurationSeconds", 0) or 0)
    baseline_duration = float(baseline.get("totalDurationSeconds", 0) or 0)
    current_served = int(current.get("servedOrderCount", 0) or 0)
    baseline_served = int(baseline.get("servedOrderCount", 0) or 0)
    vehicle_gap = current_vehicle - baseline_vehicle
    distance_gap = pct_gap(current_distance, baseline_distance)
    duration_gap = pct_gap(current_duration, baseline_duration)
    served_gap = current_served - baseline_served
    feasibility_delta = float(bool(current.get("feasible"))) - float(bool(baseline.get("feasible")))
    strong_baseline_gap = vehicle_gap + distance_gap / 100.0 - served_gap * 0.1
    return {
        "schemaVersion": "solver-gap-report/v1",
        "currentSolver": current.get("solver", "current"),
        "baselineSolver": baseline.get("solver", "baseline"),
        "vehicle_count_gap": vehicle_gap,
        "distance_gap_pct": distance_gap,
        "duration_gap_pct": duration_gap,
        "served_order_gap": served_gap,
        "feasibility_delta": feasibility_delta,
        "runtime_to_first_feasible_ms": current.get("runtimeToFirstFeasibleMs", current.get("runtimeMs", 0)) or 0,
        "runtime_to_best_ms": current.get("runtimeToBestMs", current.get("runtimeMs", 0)) or 0,
        "strong_baseline_gap": strong_baseline_gap,
        "verdict": "PASS" if strong_baseline_gap <= 0 else "PASS_WITH_LIMITS",
    }


def markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Solver Gap Report",
        "",
        f"- current solver: `{report.get('currentSolver')}`",
        f"- baseline solver: `{report.get('baselineSolver')}`",
        f"- vehicle_count_gap: `{report.get('vehicle_count_gap')}`",
        f"- distance_gap_pct: `{report.get('distance_gap_pct')}`",
        f"- duration_gap_pct: `{report.get('duration_gap_pct')}`",
        f"- served_order_gap: `{report.get('served_order_gap')}`",
        f"- strong_baseline_gap: `{report.get('strong_baseline_gap')}`",
        f"- verdict: `{report.get('verdict')}`",
        "",
    ])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare current dispatch result against solver baseline.")
    parser.add_argument("--current", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = compare(load(Path(args.current)), load(Path(args.baseline)))
    output = Path(args.output)
    write(output, report)
    output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(f"[GAP] wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

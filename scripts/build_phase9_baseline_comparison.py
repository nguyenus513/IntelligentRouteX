from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(input_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(input_dir.rglob("external_benchmark_results.json")):
        payload = read_json(path)
        for row in payload.get("results", []):
            enriched = dict(row)
            enriched["artifactPath"] = str(path)
            rows.append(enriched)
    return rows


def as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("suite", "")), str(row.get("instance", ""))


def compare(input_dir: Path) -> dict[str, Any]:
    rows = load_rows(input_dir)
    by_key: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_key[row_key(row)][str(row.get("solver", ""))] = row

    comparisons: list[dict[str, Any]] = []
    wins = 0
    ties = 0
    losses = 0
    missing_baseline = 0
    for key, solvers in sorted(by_key.items()):
        ours = solvers.get("our-dispatch-v2")
        if ours is None:
            continue
        baselines = {solver: row for solver, row in solvers.items() if solver != "our-dispatch-v2"}
        if not baselines:
            missing_baseline += 1
        for solver, baseline in sorted(baselines.items()):
            ours_feasible = bool(ours.get("feasible", False))
            baseline_feasible = bool(baseline.get("feasible", False))
            ours_distance = as_float(ours.get("totalDistance"))
            baseline_distance = as_float(baseline.get("totalDistance"))
            ours_vehicles = int(as_float(ours.get("vehicleCount")))
            baseline_vehicles = int(as_float(baseline.get("vehicleCount")))
            ours_runtime = as_float(ours.get("runtimeMs"))
            baseline_runtime = as_float(baseline.get("runtimeMs"))
            if ours_feasible and not baseline_feasible:
                verdict = "WIN"
            elif ours_feasible != baseline_feasible:
                verdict = "LOSS"
            elif ours_vehicles < baseline_vehicles:
                verdict = "WIN"
            elif ours_vehicles > baseline_vehicles:
                verdict = "LOSS"
            elif ours_distance + 1e-9 < baseline_distance:
                verdict = "WIN"
            elif ours_distance > baseline_distance + 1e-9:
                verdict = "LOSS"
            elif ours_runtime <= baseline_runtime:
                verdict = "WIN_RUNTIME"
            else:
                verdict = "TIE_QUALITY"
            if verdict.startswith("WIN"):
                wins += 1
            elif verdict == "LOSS":
                losses += 1
            else:
                ties += 1
            comparisons.append({
                "suite": key[0],
                "instance": key[1],
                "baselineSolver": solver,
                "verdict": verdict,
                "oursFeasible": ours_feasible,
                "baselineFeasible": baseline_feasible,
                "oursVehicleCount": ours_vehicles,
                "baselineVehicleCount": baseline_vehicles,
                "oursDistance": ours_distance,
                "baselineDistance": baseline_distance,
                "distanceDelta": round(ours_distance - baseline_distance, 9),
                "oursRuntimeMs": ours_runtime,
                "baselineRuntimeMs": baseline_runtime,
                "runtimeDeltaMs": round(ours_runtime - baseline_runtime, 9),
            })
    blockers = []
    if not rows:
        blockers.append("phase9-comparison-no-artifacts")
    if losses > 0:
        blockers.append("phase9-comparison-has-quality-losses")
    return {
        "schemaVersion": "phase9-baseline-comparison/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "inputDir": str(input_dir),
        "rowCount": len(rows),
        "comparisonCount": len(comparisons),
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "missingBaselineInstances": missing_baseline,
        "comparisons": comparisons,
        "blockers": blockers,
        "pass": bool(rows) and losses == 0,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 9 Baseline Comparison",
        "",
        f"- verdict: `{'PASS' if report['pass'] else 'FAIL'}`",
        f"- comparisons: `{report['comparisonCount']}`",
        f"- wins/ties/losses: `{report['wins']}/{report['ties']}/{report['losses']}`",
        f"- missing baseline instances: `{report['missingBaselineInstances']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Baseline | Verdict | Vehicles O/B | Distance O/B | Runtime O/B |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for row in report["comparisons"]:
        lines.append(
            f"| {row['suite']} | {row['instance']} | {row['baselineSolver']} | {row['verdict']} | "
            f"{row['oursVehicleCount']}/{row['baselineVehicleCount']} | "
            f"{row['oursDistance']}/{row['baselineDistance']} | "
            f"{row['oursRuntimeMs']}/{row['baselineRuntimeMs']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Phase 9 our-dispatch-v2 results against optional baselines.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    report = compare(Path(args.input_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase9_baseline_comparison.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase9_baseline_comparison.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE9 COMPARISON] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

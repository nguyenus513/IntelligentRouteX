from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase58b-vroom-vehicle-losses-v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase59-vroom-gap-analyzer-v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any] | List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def metric(row: Dict[str, Any], side: str, name: str, default: Any = None) -> Any:
    return row.get(side, {}).get(name, default)


def is_hard_fail(metrics: Dict[str, Any]) -> bool:
    return int(metrics.get("hardViolations", 0) or 0) > 0 or not bool(metrics.get("feasible", True))


def classify_gap(row: Dict[str, Any], distance_tolerance: float = 0.01) -> str:
    classification = str(row.get("classification", ""))
    champion = row.get("champion", {})
    challenger = row.get("challenger", {})
    challenger_hard = int(challenger.get("hardViolations", 0) or 0) > 0
    vroom_hard = int(champion.get("hardViolations", 0) or 0) > 0 or classification == "vroom-hard-fail"

    if classification == "vroom-timeout":
        return "vroom-timeout"
    if classification in {"vroom-hard-fail", "vroom-import-fail", "vroom-schema-error", "unsupported-mapping"}:
        return "challenger-better-feasibility" if not challenger_hard else "vroom-hard-fail"
    if vroom_hard and not challenger_hard:
        return "challenger-better-feasibility"
    if challenger_hard:
        return "challenger-hard-fail"

    vroom_vehicles = int(champion.get("vehicleCount", 0) or 0)
    challenger_vehicles = int(challenger.get("vehicleCount", 0) or 0)
    if vroom_vehicles > 0 and challenger_vehicles > vroom_vehicles:
        return "vroom-quality-win-vehicle-count"
    if challenger_vehicles > 0 and challenger_vehicles < vroom_vehicles:
        return "challenger-quality-win-vehicle-count"

    vroom_distance = float(champion.get("totalDistance", 0.0) or 0.0)
    challenger_distance = float(challenger.get("totalDistance", 0.0) or 0.0)
    tolerance = max(1e-9, abs(vroom_distance) * distance_tolerance)
    if vroom_distance > 0 and challenger_distance > vroom_distance + tolerance:
        return "vroom-quality-win-distance"
    if challenger_distance > 0 and challenger_distance + tolerance < vroom_distance:
        return "challenger-quality-win-distance"
    return "tie"


def analyze_rows(rows: List[Dict[str, Any]], distance_tolerance: float = 0.01) -> Dict[str, Any]:
    analyzed_rows = []
    counts: Dict[str, int] = {}
    vehicle_gaps = []
    distance_gaps = []
    challenger_hard_fail_count = 0
    vroom_hard_fail_count = 0
    vroom_timeout_count = 0

    for row in rows:
        gap_classification = classify_gap(row, distance_tolerance)
        counts[gap_classification] = counts.get(gap_classification, 0) + 1
        champion = row.get("champion", {})
        challenger = row.get("challenger", {})
        challenger_hard = int(challenger.get("hardViolations", 0) or 0) > 0
        source_classification = row.get("classification")
        vroom_hard = source_classification == "vroom-hard-fail" or (int(champion.get("hardViolations", 0) or 0) > 0 and source_classification != "vroom-timeout")
        if challenger_hard:
            challenger_hard_fail_count += 1
        if vroom_hard:
            vroom_hard_fail_count += 1
        if source_classification == "vroom-timeout":
            vroom_timeout_count += 1

        vroom_vehicles = champion.get("vehicleCount")
        challenger_vehicles = challenger.get("vehicleCount")
        vehicle_gap = None
        if vroom_vehicles is not None and challenger_vehicles is not None:
            vehicle_gap = int(challenger_vehicles) - int(vroom_vehicles)
            if not challenger_hard and not vroom_hard and source_classification != "vroom-timeout":
                vehicle_gaps.append(vehicle_gap)

        vroom_distance = champion.get("totalDistance")
        challenger_distance = challenger.get("totalDistance")
        distance_gap = None
        distance_gap_pct = None
        if vroom_distance is not None and challenger_distance is not None:
            distance_gap = float(challenger_distance) - float(vroom_distance)
            if float(vroom_distance or 0.0) > 0:
                distance_gap_pct = distance_gap / float(vroom_distance)
            if not challenger_hard and not vroom_hard and source_classification != "vroom-timeout":
                distance_gaps.append(distance_gap)

        analyzed_rows.append(
            {
                "instance": row.get("instance"),
                "sourceClassification": row.get("classification"),
                "gapClassification": gap_classification,
                "vehicleGapChallengerMinusVroom": vehicle_gap,
                "distanceGapChallengerMinusVroom": distance_gap,
                "distanceGapPct": distance_gap_pct,
                "vroomHardViolations": champion.get("hardViolations"),
                "challengerHardViolations": challenger.get("hardViolations"),
                "vroomRuntimeMs": row.get("vroomRuntimeMs"),
                "challengerRuntimeMs": challenger.get("runtimeMs"),
                "routePoolSkippedDueHardBudget": bool(row.get("challenger", {}).get("routePoolSkippedDueHardBudget", False)),
            }
        )

    recommendations = recommend_next_optimization(counts, vehicle_gaps, distance_gaps)
    return {
        "schemaVersion": "phase59-vroom-gap-analyzer/v1",
        "classificationCounts": counts,
        "challengerHardFailCount": challenger_hard_fail_count,
        "vroomHardFailCount": vroom_hard_fail_count,
        "vroomTimeoutCount": vroom_timeout_count,
        "vehicleGapSummary": summarize_numbers(vehicle_gaps),
        "distanceGapSummary": summarize_numbers(distance_gaps),
        "recommendations": recommendations,
        "rows": analyzed_rows,
    }


def summarize_numbers(values: List[float | int]) -> Dict[str, Any]:
    if not values:
        return {"count": 0, "sum": 0, "mean": None, "max": None, "min": None}
    return {"count": len(values), "sum": sum(values), "mean": sum(values) / len(values), "max": max(values), "min": min(values)}


def recommend_next_optimization(counts: Dict[str, int], vehicle_gaps: List[int], distance_gaps: List[float]) -> List[str]:
    recommendations = []
    vroom_failures = counts.get("challenger-better-feasibility", 0) + counts.get("vroom-timeout", 0) + counts.get("vroom-hard-fail", 0)
    vehicle_gap_count = counts.get("vroom-quality-win-vehicle-count", 0)
    distance_gap_count = counts.get("vroom-quality-win-distance", 0)
    if vroom_failures >= max(vehicle_gap_count, distance_gap_count, 1):
        recommendations.append("keep Challenger Phase 56F as stability baseline")
    if vehicle_gap_count > 0 or any(gap > 0 for gap in vehicle_gaps):
        recommendations.append("route elimination or route-pool fast mode")
    if distance_gap_count > 0 or any(gap > 0 for gap in distance_gaps):
        recommendations.append("bounded distance polish")
    if not recommendations:
        recommendations.append("production hardening and broader certification")
    return recommendations


def markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Phase 59 VROOM Gap Analyzer",
        "",
        "## Aggregate",
        "",
        f"- Challenger hard fails: {summary['challengerHardFailCount']}",
        f"- VROOM hard fails: {summary['vroomHardFailCount']}",
        f"- VROOM timeouts: {summary['vroomTimeoutCount']}",
        f"- Classifications: `{json.dumps(summary['classificationCounts'], sort_keys=True)}`",
        "",
        "## Recommendations",
        "",
    ]
    lines.extend(f"- {item}" for item in summary.get("recommendations", []))
    lines.extend(["", "## Per Instance", "", "| Instance | Gap Class | Vehicle Gap | Distance Gap | Source |", "|---|---|---:|---:|---|"])
    for row in summary.get("rows", []):
        lines.append(f"| {row['instance']} | {row['gapClassification']} | {row['vehicleGapChallengerMinusVroom']} | {row['distanceGapChallengerMinusVroom']} | {row['sourceClassification']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze VROOM vs Phase 56F gaps from Phase 58B comparator artifacts.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--distance-tolerance", type=float, default=0.01)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    rows = read_json(input_dir / "per_instance_comparison.json")
    summary = analyze_rows(rows, args.distance_tolerance)
    write_json(output_dir / "phase59_vroom_gap_summary.json", summary)
    (output_dir / "phase59_vroom_gap_summary.md").parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase59_vroom_gap_summary.md").write_text(markdown(summary), encoding="utf-8")
    print(f"[PHASE59 VROOM GAP ANALYZER] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

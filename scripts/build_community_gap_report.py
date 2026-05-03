from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def load_results(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for row in payload.get("results", []):
        stage = row.get("stage")
        if stage is not None and stage != "A-academic-correctness":
            continue
        vehicle_count = as_int(row.get("vehicleCount"))
        best_vehicle_count = as_int(row.get("bestKnownVehicleCount"))
        vehicle_gap = max(0, vehicle_count - best_vehicle_count) if vehicle_count and best_vehicle_count else 0
        problem_type = str(row.get("problemType", ""))
        rows.append({
            "suite": row.get("suite", ""),
            "instance": row.get("instance", ""),
            "problemType": problem_type,
            "vehicleCount": vehicle_count,
            "bestKnownVehicleCount": best_vehicle_count,
            "vehicleGap": vehicle_gap,
            "totalDistance": as_float(row.get("totalDistance")),
            "bestKnownDistance": as_float(row.get("bestKnownDistance")),
            "objectiveGapPercent": as_float(row.get("objectiveGapPercent")),
            "feasible": bool(row.get("feasible", False)),
            "verdict": row.get("verdict", ""),
            "verdictReasons": row.get("verdictReasons", []),
            "recommendedOperator": recommend_operator(problem_type, vehicle_gap),
            "solutionPath": row.get("solutionPath", ""),
        })
    return rows


def recommend_operator(problem_type: str, vehicle_gap: int) -> str:
    if vehicle_gap <= 0:
        return "monitor"
    if problem_type == "PDPTW":
        return "pair-aware-route-elimination-ejection"
    return "route-elimination-cross-exchange"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blocker_counts = Counter()
    for row in rows:
        if not row["feasible"]:
            blocker_counts["infeasible"] += 1
        if row["vehicleGap"] > 0:
            blocker_counts["vehicle-count-gap"] += 1
    return {
        "schemaVersion": "community-gap-report/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "rowCount": len(rows),
        "vehicleGapSum": sum(row["vehicleGap"] for row in rows),
        "vehicleGapMax": max((row["vehicleGap"] for row in rows), default=0),
        "gapInstanceCount": sum(1 for row in rows if row["vehicleGap"] > 0),
        "blockerCounts": dict(sorted(blocker_counts.items())),
        "worstRows": sorted(rows, key=lambda row: (-row["vehicleGap"], -row["objectiveGapPercent"], row["instance"])),
        "pass": bool(rows) and all(row["feasible"] and row["vehicleGap"] == 0 for row in rows),
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Community Gap Report",
        "",
        f"- verdict: `{'PASS' if report['pass'] else 'PASS_WITH_LIMITS'}`",
        f"- rows: `{report['rowCount']}`",
        f"- vehicle gap sum: `{report['vehicleGapSum']}`",
        f"- vehicle gap max: `{report['vehicleGapMax']}`",
        f"- gap instance count: `{report['gapInstanceCount']}`",
        f"- blocker counts: `{report['blockerCounts']}`",
        "",
        "| Suite | Instance | Type | Vehicles | BKS Vehicles | Gap | Distance Gap % | Recommended Operator |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in report["worstRows"]:
        lines.append(
            f"| {row['suite']} | {row['instance']} | {row['problemType']} | {row['vehicleCount']} | "
            f"{row['bestKnownVehicleCount']} | {row['vehicleGap']} | {row['objectiveGapPercent']} | {row['recommendedOperator']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build vehicle-count and objective gap report from community certification results.")
    parser.add_argument("--certification-results", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    report = summarize(load_results(Path(args.certification_results)))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "community_gap_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "community_gap_report.md").write_text(markdown(report), encoding="utf-8")
    print(f"[COMMUNITY GAP] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


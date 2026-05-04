from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "final" / "vroom_capability_full_v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def fair_classify(row: Dict[str, Any], distance_tolerance: float = 0.01) -> str:
    champion = row.get("champion", {})
    challenger = row.get("challenger", {})
    vroom_feasible = bool(row.get("vroomFeasibleByInternalChecker")) and int(champion.get("hardViolations", 0) or 0) == 0
    challenger_feasible = int(challenger.get("hardViolations", 0) or 0) == 0 and not challenger.get("overBudget")
    if not challenger_feasible:
        return "challenger-hard-fail"
    if row.get("classification") in {"vroom-timeout", "vroom-unavailable"}:
        return f"{row.get('classification')}-no-quality-score"
    if row.get("classification") in {"vroom-import-fail", "unsupported-mapping", "vroom-schema-error"}:
        return "semantic-mismatch-no-quality-score"
    if not vroom_feasible:
        return "challenger-better-feasibility"
    vroom_vehicles = int(champion.get("vehicleCount", 0) or 0)
    challenger_vehicles = int(challenger.get("vehicleCount", 0) or 0)
    if challenger_vehicles < vroom_vehicles:
        return "both-feasible-challenger-vehicle-win"
    if challenger_vehicles > vroom_vehicles:
        return "both-feasible-vroom-vehicle-win"
    vroom_distance = float(champion.get("totalDistance", 0.0) or 0.0)
    challenger_distance = float(challenger.get("totalDistance", 0.0) or 0.0)
    tolerance = max(1e-9, vroom_distance * distance_tolerance)
    if abs(challenger_distance - vroom_distance) <= tolerance:
        return "both-feasible-tie"
    return "both-feasible-challenger-distance-win" if challenger_distance < vroom_distance else "both-feasible-vroom-distance-win"


def run(input_dir: Path, output_dir: Path) -> Dict[str, Any]:
    rows = read_json(input_dir / "vroom_comparator" / "per_instance_comparison.json")
    fair_rows = [{"instance": row.get("instance"), "fairClassification": fair_classify(row), "sourceClassification": row.get("classification")} for row in rows]
    counts: Dict[str, int] = {}
    for row in fair_rows:
        counts[row["fairClassification"]] = counts.get(row["fairClassification"], 0) + 1
    summary = {"schemaVersion": "phase76-vroom-fair-quality-report/v1", "inputDir": str(input_dir), "classificationCounts": counts, "rows": fair_rows}
    write_json(output_dir / "fair_quality_report.json", summary)
    (output_dir / "fair_quality_report.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    lines = ["# Phase 76 VROOM Fair Quality Report", "", f"Counts: `{json.dumps(summary['classificationCounts'], sort_keys=True)}`", "", "| Instance | Fair Classification | Source |", "|---|---|---|"]
    for row in summary.get("rows", []):
        lines.append(f"| {row['instance']} | {row['fairClassification']} | {row['sourceClassification']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fair VROOM quality report that compares quality only when both solvers are feasible.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default="artifacts/benchmark/phase76_vroom_fair_quality_v1")
    args = parser.parse_args()
    run(Path(args.input_dir), Path(args.output_dir))
    print(f"[PHASE76 VROOM FAIR QUALITY] wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

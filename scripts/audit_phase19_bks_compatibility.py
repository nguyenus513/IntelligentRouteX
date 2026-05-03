from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from external_benchmark_support import check_solution
from parse_solomon_vrptw import parse_solomon
from reference_solution_loader import find_reference_solution
from run_academic_max_quality import parse_duration_ms, write_json
from run_phase13_hgs_route_pool_targets import instance_path
from solomon_distance_semantics import DISTANCE_MODES, instance_with_distance_mode

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase19-bks-compatibility-v1"


def instance_fingerprint(instance: dict[str, Any]) -> dict[str, Any]:
    nodes = instance.get("nodes", [])
    digest_input = "|".join(
        f"{node.get('id')}:{node.get('x')}:{node.get('y')}:{node.get('demand')}:{node.get('readyTime')}:{node.get('dueTime')}:{node.get('serviceTime')}"
        for node in nodes
    )
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]
    depot = next((node for node in nodes if str(node.get("id")) == str(instance.get("depotNodeId", "0"))), {})
    return {
        "instanceName": instance.get("instanceName"),
        "problemType": instance.get("problemType"),
        "nodeCount": len(nodes),
        "customerCount": max(0, len(nodes) - 1),
        "vehicleCount": instance.get("vehicleCount"),
        "capacity": instance.get("capacity"),
        "depotReadyTime": depot.get("readyTime"),
        "depotDueTime": depot.get("dueTime"),
        "depotServiceTime": depot.get("serviceTime"),
        "coordinateChecksum": digest,
        "bestKnown": instance.get("bestKnown", {}),
        "sourcePath": instance.get("sourcePath"),
    }


def distance_semantics(instance: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    bks = instance.get("bestKnown", {})
    for mode in DISTANCE_MODES:
        candidate_instance = instance_with_distance_mode(instance, mode)
        checked = check_solution(candidate_instance, solution)
        rows.append({
            "mode": mode,
            "feasible": checked.get("feasible"),
            "vehicleCount": checked.get("vehicleCount"),
            "totalDistance": checked.get("totalDistance"),
            "bestKnownDistance": bks.get("objective"),
            "objectiveGapPercent": checked.get("objectiveGapPercent"),
            "timeWindowViolationCount": checked.get("timeWindowViolationCount"),
            "capacityViolationCount": checked.get("capacityViolationCount"),
            "unservedRequestCount": checked.get("unservedRequestCount"),
            "violations": checked.get("violations", []),
        })
    return rows


def checker_semantics(instance: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, Any]]:
    variants = []
    for epsilon in (1e-9, 1e-6, 1e-3):
        variants.append(check_solution_variant(instance, solution, epsilon=epsilon, enforce_depot_due=True, include_depot_service=True))
        variants.append(check_solution_variant(instance, solution, epsilon=epsilon, enforce_depot_due=False, include_depot_service=False))
    return variants


def check_solution_variant(instance: dict[str, Any], solution: dict[str, Any], epsilon: float, enforce_depot_due: bool, include_depot_service: bool) -> dict[str, Any]:
    depot = str(instance.get("depotNodeId", "0"))
    nodes = {str(node["id"]): node for node in instance.get("nodes", [])}
    index = {str(node["id"]): position for position, node in enumerate(instance.get("nodes", []))}
    matrix = instance.get("distanceMatrix", [])
    routes = [[str(stop) for stop in route] for route in solution.get("routes", [])]
    time_violations = 0
    first_violation = None
    for route_index, route in enumerate(routes):
        elapsed = 0.0
        for previous, current in zip(route, route[1:]):
            elapsed += float(matrix[index[previous]][index[current]])
            node = nodes[current]
            ready = float(node.get("readyTime", 0.0))
            due = float(node.get("dueTime", 1e18))
            if elapsed < ready:
                elapsed = ready
            should_enforce_due = current != depot or enforce_depot_due
            if should_enforce_due and elapsed > due + epsilon:
                time_violations += 1
                if first_violation is None:
                    first_violation = {"routeIndex": route_index, "node": current, "arrival": elapsed, "due": due, "epsilon": epsilon}
            if current != depot or include_depot_service:
                elapsed += float(node.get("serviceTime", 0.0))
    return {
        "mode": f"epsilon={epsilon};depotDue={enforce_depot_due};depotService={include_depot_service}",
        "epsilon": epsilon,
        "enforceDepotDue": enforce_depot_due,
        "includeDepotService": include_depot_service,
        "timeWindowViolationCount": time_violations,
        "firstViolation": first_violation,
        "feasibleByTimeWindows": time_violations == 0,
    }


def audit(instance_name: str, data_source: str, incumbent_solution: Path, output_dir: Path) -> dict[str, Any]:
    instance = parse_solomon(instance_path("solomon", instance_name, data_source))
    solution = json.loads(incumbent_solution.read_text(encoding="utf-8"))
    incumbent_checked = check_solution(instance, solution)
    reference = find_reference_solution(instance_name, REPO_ROOT, str(instance.get("depotNodeId", "0")))
    reference_checked = check_solution(instance, reference) if reference is not None else None
    distance_rows = distance_semantics(instance, solution)
    checker_rows = checker_semantics(instance, solution)
    conclusion = compatibility_conclusion(instance, incumbent_checked, distance_rows, reference_checked)
    report = {
        "schemaVersion": "phase19-bks-compatibility-audit/v1",
        "instance": instance_name,
        "dataSource": data_source,
        "instanceFingerprint": instance_fingerprint(instance),
        "incumbentSolutionPath": str(incumbent_solution),
        "incumbentChecked": incumbent_checked,
        "distanceSemantics": distance_rows,
        "checkerSemantics": checker_rows,
        "referenceRouteAvailable": reference is not None,
        "referenceRoute": None if reference is None else {"path": reference.get("referencePath"), "routeCount": len(reference.get("routes", []))},
        "referenceRouteChecked": reference_checked,
        "compatibilityConclusion": conclusion,
        "recommendedNextStep": recommended_next_step(conclusion, reference_checked),
    }
    write_json(output_dir / "phase19_bks_compatibility_audit.json", report)
    (output_dir / "phase19_bks_compatibility_audit.md").write_text(markdown(report), encoding="utf-8")
    return report


def compatibility_conclusion(instance: dict[str, Any], incumbent_checked: dict[str, Any], distance_rows: Sequence[dict[str, Any]], reference_checked: dict[str, Any] | None) -> str:
    if reference_checked is not None:
        if reference_checked.get("feasible") and int(reference_checked.get("vehicleCount") or 10**9) <= int(instance.get("bestKnown", {}).get("vehicleCount") or 0):
            return "reference-route-feasible-model-compatible"
        return "reference-route-infeasible-model-mismatch-suspected"
    feasible_modes = [row for row in distance_rows if row.get("feasible")]
    if not feasible_modes or not incumbent_checked.get("feasible"):
        return "incumbent-infeasible-model-or-checker-mismatch"
    return "model-compatible-reference-route-missing-solver-gap-likely"


def recommended_next_step(conclusion: str, reference_checked: dict[str, Any] | None) -> str:
    if conclusion == "reference-route-feasible-model-compatible":
        return "import-reference-routes-into-route-pool-and-seed-learned-ranking"
    if conclusion == "reference-route-infeasible-model-mismatch-suspected":
        return "compare-reference-arrival-trace-against-parser-distance-service-semantics"
    if reference_checked is None:
        return "obtain-or-generate-reference-14-vehicle-route-file-for-rc101"
    return "run-stronger-offline-search-after-confirming-reference-compatibility"


def markdown(report: dict[str, Any]) -> str:
    fp = report["instanceFingerprint"]
    lines = [
        "# Phase 19 BKS Compatibility Audit",
        "",
        f"- instance: `{report['instance']}`",
        f"- node/customer count: `{fp['nodeCount']}/{fp['customerCount']}`",
        f"- BKS: `{fp['bestKnown']}`",
        f"- incumbent vehicles/distance: `{report['incumbentChecked'].get('vehicleCount')}/{report['incumbentChecked'].get('totalDistance')}`",
        f"- reference route available: `{report['referenceRouteAvailable']}`",
        f"- conclusion: `{report['compatibilityConclusion']}`",
        f"- next step: `{report['recommendedNextStep']}`",
        "",
        "## Distance Semantics",
        "",
        "| Mode | Feasible | Vehicles | Distance | Gap % | TW Violations | Violations |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["distanceSemantics"]:
        lines.append(
            f"| {row['mode']} | {row['feasible']} | {row['vehicleCount']} | {row['totalDistance']} | {row['objectiveGapPercent']} | "
            f"{row['timeWindowViolationCount']} | {row['violations']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Solomon BKS/reference compatibility for Phase 19.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--instance", default="RC101")
    parser.add_argument("--data-source", choices=("official", "auto"), default="auto")
    parser.add_argument("--incumbent-solution", required=True)
    parser.add_argument("--time-limit", default="15s")
    args = parser.parse_args(argv)
    parse_duration_ms(args.time_limit)
    audit(args.instance, args.data_source, Path(args.incumbent_solution), Path(args.output_dir))
    print(f"[PHASE19 BKS COMPATIBILITY] wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Sequence

from parse_solomon_vrptw import parse_solomon
from run_dispatch_benchmark_certification_suite import HOMBERGER_BEST_KNOWN, REPO_ROOT


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "pyvrp-baseline"
DEFAULT_INSTANCES = ("C1_10_1", "R1_10_1", "RC1_10_1")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_homberger(instance: str) -> Dict[str, Any]:
    path = REPO_ROOT / "benchmarks" / "external" / "official" / "homberger" / f"{instance}.txt"
    normalized = parse_solomon(path)
    normalized["benchmarkFamily"] = "homberger"
    if instance in HOMBERGER_BEST_KNOWN:
        normalized["bestKnown"] = HOMBERGER_BEST_KNOWN[instance]
    return normalized


def pyvrp_available() -> bool:
    return importlib.util.find_spec("pyvrp") is not None


def build_pyvrp_model(normalized: Dict[str, Any]) -> Any:
    from pyvrp import Model

    nodes = normalized["nodes"]
    depot_node = nodes[0]
    model = Model()
    depot = model.add_depot(
        x=float(depot_node["x"]),
        y=float(depot_node["y"]),
        tw_early=int(round(float(depot_node.get("readyTime", 0.0)))),
        tw_late=int(round(float(depot_node.get("dueTime", 0.0)))),
        service_duration=int(round(float(depot_node.get("serviceTime", 0.0)))),
        name=str(depot_node["id"]),
    )
    locations = [depot]
    for node in nodes[1:]:
        locations.append(
            model.add_client(
                x=float(node["x"]),
                y=float(node["y"]),
                delivery=int(round(float(node.get("demand", 0)))),
                service_duration=int(round(float(node.get("serviceTime", 0.0)))),
                tw_early=int(round(float(node.get("readyTime", 0.0)))),
                tw_late=int(round(float(node.get("dueTime", 0.0)))),
                name=str(node["id"]),
            )
        )
    model.add_vehicle_type(
        num_available=int(normalized.get("vehicleCount", len(nodes))),
        capacity=int(round(float(normalized.get("capacity", 0)))),
        start_depot=depot,
        end_depot=depot,
        fixed_cost=1_000_000,
        unit_distance_cost=1,
        unit_duration_cost=0,
    )
    for left_index, left in enumerate(nodes):
        for right_index, right in enumerate(nodes):
            if left_index == right_index:
                continue
            distance = int(round(math.hypot(float(left["x"]) - float(right["x"]), float(left["y"]) - float(right["y"])) * 10.0))
            model.add_edge(locations[left_index], locations[right_index], distance=distance, duration=distance)
    return model


def parse_duration_ms(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("ms"):
        return int(float(text[:-2]))
    if text.endswith("s"):
        return int(float(text[:-1]) * 1000)
    if text.endswith("m"):
        return int(float(text[:-1]) * 60_000)
    if text.endswith("h"):
        return int(float(text[:-1]) * 3_600_000)
    return int(float(text) * 1000)


def run_instance(instance: str, time_limit_ms: int) -> Dict[str, Any]:
    normalized = load_homberger(instance)
    best = normalized.get("bestKnown", {})
    if not pyvrp_available():
        return {
            "instance": instance,
            "solver": "pyvrp-hgs",
            "feasible": False,
            "runtimeMs": 0,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["pyvrp-package-not-installed"],
            "bksVehicleCount": best.get("vehicleCount"),
            "bksDistance": best.get("objective"),
            "requestedTimeLimitMs": time_limit_ms,
        }
    try:
        from pyvrp.stop import MaxRuntime

        model = build_pyvrp_model(normalized)
        started = time.perf_counter()
        result = model.solve(MaxRuntime(max(0.1, time_limit_ms / 1000.0)), seed=1, display=False)
        runtime_ms = int((time.perf_counter() - started) * 1000)
        solution = result.best
        feasible = bool(result.is_feasible())
        vehicle_count = int(solution.num_routes())
        total_distance = float(solution.distance()) / 10.0
        bks_vehicle_count = best.get("vehicleCount")
        bks_distance = best.get("objective")
        vehicle_gap = None if bks_vehicle_count is None else vehicle_count - int(bks_vehicle_count)
        distance_gap_percent = None if not bks_distance else (total_distance - float(bks_distance)) / float(bks_distance) * 100.0
        if feasible and (bks_vehicle_count is None or vehicle_count <= int(bks_vehicle_count)):
            verdict = "PASS"
            reasons = ["pyvrp-baseline-feasible-within-vehicle-target"]
        elif feasible:
            verdict = "PASS_WITH_LIMITS"
            reasons = ["pyvrp-baseline-above-best-known-vehicles"]
        else:
            verdict = "PASS_WITH_LIMITS"
            reasons = ["pyvrp-baseline-infeasible-within-budget"]
        return {
            "instance": instance,
            "solver": "pyvrp-hgs",
            "feasible": feasible,
            "runtimeMs": runtime_ms,
            "verdict": verdict,
            "verdictReasons": reasons,
            "vehicleCount": vehicle_count,
            "totalDistance": total_distance,
            "bksVehicleCount": bks_vehicle_count,
            "bksDistance": bks_distance,
            "vehicleGap": vehicle_gap,
            "distanceGapPercent": distance_gap_percent,
            "requestedTimeLimitMs": time_limit_ms,
        }
    except Exception as exc:
        return {
            "instance": instance,
            "solver": "pyvrp-hgs",
            "feasible": False,
            "runtimeMs": 0,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["pyvrp-adapter-runtime-error"],
            "error": str(exc),
            "bksVehicleCount": best.get("vehicleCount"),
            "bksDistance": best.get("objective"),
            "requestedTimeLimitMs": time_limit_ms,
        }


def markdown(rows: Sequence[Dict[str, Any]]) -> str:
    final = "PASS" if rows and all(row["verdict"] == "PASS" for row in rows) else "EVIDENCE_GAP"
    lines = ["# PyVRP/HGS Baseline", "", f"FINAL_VERDICT = {final}", ""]
    lines.append("| Instance | Feasible | Vehicles | BKS Vehicles | Distance | BKS Distance | Verdict | Reasons |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |")
    for row in rows:
        lines.append(
            f"| {row['instance']} | {row.get('feasible')} | {row.get('vehicleCount', 'n/a')} | {row.get('bksVehicleCount')} | {row.get('totalDistance', 'n/a')} | {row.get('bksDistance')} | {row['verdict']} | {', '.join(row.get('verdictReasons', []))} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PyVRP/HGS baseline if the optional pyvrp package is installed.")
    parser.add_argument("--instances", default=",".join(DEFAULT_INSTANCES))
    parser.add_argument("--time-limit", default="30m")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    rows = [run_instance(instance, parse_duration_ms(args.time_limit)) for instance in instances]
    output_root = Path(args.output_root)
    result = {"schemaVersion": "pyvrp-baseline/v1", "pyvrpInstalled": pyvrp_available(), "results": rows}
    write_json(output_root / "pyvrp_results.json", result)
    (output_root / "pyvrp_report.md").write_text(markdown(rows), encoding="utf-8")
    print(f"[PYVRP BASELINE JSON] {output_root / 'pyvrp_results.json'}")
    print(f"[PYVRP BASELINE REPORT] {output_root / 'pyvrp_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

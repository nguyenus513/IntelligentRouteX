from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERNIGHT = REPO_ROOT / "artifacts" / "benchmark" / "overnight_no_vroom_20260505_010106"
DEFAULT_VROOM_SMOKE = REPO_ROOT / "artifacts" / "benchmark" / "vroom_live_smoke_20260505"
DEFAULT_VROOM_LILIM = REPO_ROOT / "artifacts" / "benchmark" / "vroom_lilim8_live_20260505"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "benchmark" / "community_benchmark_tables_v2"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_read_json(path: Path, default: Any, missing_inputs: list[str] | None = None) -> Any:
    if not path.exists():
        if missing_inputs is not None:
            missing_inputs.append(str(path))
        return default
    return read_json(path)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "-"
        return f"{value:.{digits}f}"
    return str(value)


def mean(values: Iterable[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def stdev(values: Iterable[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.stdev(vals) if len(vals) > 1 else 0.0 if len(vals) == 1 else None


def median(values: Iterable[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def instance_scale(row: dict[str, Any]) -> str:
    served = row.get("servedRequestCount") or 0
    if served <= 100:
        return "small"
    if served <= 400:
        return "medium"
    return "large"


def gap_pct(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline in (None, 0):
        return None
    return (value - baseline) / baseline * 100.0


def load_phase15_rows(overnight: Path, missing_inputs: list[str] | None = None) -> list[dict[str, Any]]:
    path = overnight / "07_phase15_large_community" / "phase15_large_benchmark_results.json"
    return safe_read_json(path, {}, missing_inputs).get("results", [])


def paired_solver_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_key[(row.get("suite", ""), row.get("instance", ""))][row.get("solver", "")] = row
    paired: list[dict[str, Any]] = []
    for (suite, instance), solvers in sorted(by_key.items()):
        ours = solvers.get("our-dispatch-v2")
        ortools = solvers.get("ortools-baseline")
        if not ours or not ortools:
            continue
        baseline_distance = ortools.get("totalDistance") if ortools.get("feasible") else None
        baseline_vehicle = ortools.get("vehicleCount") if ortools.get("feasible") else None
        paired.append(
            {
                "dataset": suite,
                "scale": instance_scale(ours),
                "instance": instance,
                "time_limit_sec": (ours.get("phase15TimeLimitMs") or 0) / 1000.0,
                "bks_vehicle_count": ours.get("bestKnownVehicleCount"),
                "bks_distance": ours.get("bestKnownDistance"),
                "ortools_vehicle_count": ortools.get("vehicleCount"),
                "ortools_distance": ortools.get("totalDistance"),
                "ortools_feasible": bool(ortools.get("feasible")),
                "ours_vehicle_count": ours.get("vehicleCount"),
                "ours_distance": ours.get("totalDistance"),
                "ours_feasible": bool(ours.get("feasible")),
                "ours_runtime_sec": (ours.get("runtimeMs") or 0) / 1000.0,
                "ortools_runtime_sec": (ortools.get("runtimeMs") or 0) / 1000.0,
                "vehicle_gap_vs_ortools": (ours.get("vehicleCount") - baseline_vehicle) if baseline_vehicle is not None and ours.get("vehicleCount") is not None else None,
                "distance_gap_vs_ortools_pct": gap_pct(ours.get("totalDistance"), baseline_distance) if ours.get("feasible") and ortools.get("feasible") else None,
                "distance_gap_vs_bks_pct": gap_pct(ours.get("totalDistance"), ours.get("bestKnownDistance")) if ours.get("feasible") else None,
                "capacity_violations": ours.get("capacityViolationCount"),
                "time_window_violations": ours.get("timeWindowViolationCount"),
                "pickup_delivery_violations": ours.get("pickupBeforeDropoffViolationCount"),
                "vehicle_limit_violations": ours.get("vehicleLimitViolationCount"),
            }
        )
    return paired


def aggregate_phase15(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["dataset"], row["scale"])].append(row)
    summary: list[dict[str, Any]] = []
    for (dataset, scale), group in sorted(groups.items()):
        feasible = [r for r in group if r["ours_feasible"]]
        paired_feasible = [r for r in group if r["ours_feasible"] and r["ortools_feasible"]]
        summary.append(
            {
                "dataset": dataset,
                "scale": scale,
                "instances": len(group),
                "ours_feasible_rate_pct": len(feasible) / len(group) * 100.0 if group else None,
                "avg_vehicle_gap_vs_ortools": mean(r["vehicle_gap_vs_ortools"] for r in paired_feasible),
                "avg_distance_gap_vs_ortools_pct": mean(r["distance_gap_vs_ortools_pct"] for r in paired_feasible),
                "std_distance_gap_vs_ortools_pct": stdev(r["distance_gap_vs_ortools_pct"] for r in paired_feasible),
                "median_distance_gap_vs_ortools_pct": median(r["distance_gap_vs_ortools_pct"] for r in paired_feasible),
                "avg_distance_gap_vs_bks_pct": mean(r["distance_gap_vs_bks_pct"] for r in feasible),
                "avg_runtime_sec": mean(r["ours_runtime_sec"] for r in group),
                "std_runtime_sec": stdev(r["ours_runtime_sec"] for r in group),
                "paired_feasible_instances": len(paired_feasible),
                "hard_violation_rows": sum(1 for r in group if (r.get("capacity_violations") or 0) + (r.get("time_window_violations") or 0) + (r.get("pickup_delivery_violations") or 0) + (r.get("vehicle_limit_violations") or 0) > 0),
            }
        )
    return summary


def load_vroom_rows(root: Path, suite_name: str, missing_inputs: list[str] | None = None) -> list[dict[str, Any]]:
    path = root / "vroom_comparator" / "per_instance_comparison.json"
    rows = safe_read_json(path, [], missing_inputs)
    out: list[dict[str, Any]] = []
    for row in rows:
        champion = row.get("champion") or {}
        challenger = row.get("challenger") or {}
        out.append(
            {
                "suite": suite_name,
                "instance": row.get("instance"),
                "vroom_status": row.get("vroomStatus"),
                "vroom_feasible": bool(row.get("vroomFeasibleByInternalChecker")),
                "vroom_runtime_ms": row.get("vroomRuntimeMs"),
                "vroom_vehicle_count": champion.get("vehicleCount"),
                "vroom_distance": champion.get("totalDistance"),
                "ours_vehicle_count": challenger.get("vehicleCount"),
                "ours_distance": challenger.get("totalDistance"),
                "ours_feasible": (challenger.get("hardViolations") == 0),
                "vehicle_gap_vs_vroom": (challenger.get("vehicleCount") - champion.get("vehicleCount")) if row.get("vroomFeasibleByInternalChecker") and champion.get("vehicleCount") is not None and challenger.get("vehicleCount") is not None else None,
                "distance_gap_vs_vroom_pct": gap_pct(challenger.get("totalDistance"), champion.get("totalDistance")) if row.get("vroomFeasibleByInternalChecker") and champion.get("totalDistance") else None,
                "timeout": row.get("vroomStatus") == "vroom-timeout",
                "vroom_error_class": row.get("vroomStatus") if row.get("vroomStatus") != "ok" else "-",
            }
        )
    return out


def aggregate_vroom(rows: list[dict[str, Any]]) -> dict[str, Any]:
    feasible = [r for r in rows if r["vroom_feasible"]]
    comparable = [r for r in rows if r["vroom_feasible"] and r["ours_feasible"]]
    return {
        "rows": len(rows),
        "vroom_ok_rows": sum(1 for r in rows if r["vroom_status"] == "ok"),
        "vroom_feasible_rate_pct": len(feasible) / len(rows) * 100.0 if rows else None,
        "vroom_timeout_rate_pct": sum(1 for r in rows if r["timeout"]) / len(rows) * 100.0 if rows else None,
        "comparable_rows": len(comparable),
        "avg_vehicle_gap_vs_vroom": mean(r["vehicle_gap_vs_vroom"] for r in comparable),
        "avg_distance_gap_vs_vroom_pct": mean(r["distance_gap_vs_vroom_pct"] for r in comparable),
        "std_distance_gap_vs_vroom_pct": stdev(r["distance_gap_vs_vroom_pct"] for r in comparable),
    }


def load_food(overnight: Path, missing_inputs: list[str] | None = None) -> dict[str, Any]:
    data = safe_read_json(overnight / "11_food_dispatch_quality" / "food_dispatch_quality_results.json", {}, missing_inputs)
    metrics: dict[str, Any] = {}
    for layer in data.get("layers", []):
        metrics.update(layer.get("metrics") or {})
    return {
        "row_count": data.get("rowCount"),
        "served_order_rate_pct": (metrics.get("servedOrderRate") or 0) * 100.0,
        "late_order_rate_pct": (metrics.get("lateOrderRate") or 0) * 100.0,
        "p95_delay": metrics.get("p95DelayMax"),
        "p95_food_on_vehicle_time": metrics.get("p95FoodOnVehicleTimeMax"),
        "avg_order_to_delivery_time": metrics.get("avgOrderToDeliveryTime"),
        "p95_order_to_delivery_time": metrics.get("p95OrderToDeliveryTimeMax"),
        "courier_utilization_pct": (metrics.get("courierUtilization") or 0) * 100.0,
        "assignment_fairness_gini": metrics.get("assignmentFairnessGini"),
        "courier_shift_violations": metrics.get("courierShiftViolation"),
        "pickup_before_dropoff_violations": metrics.get("pickupBeforeDropoffViolation"),
        "cost_per_order": "not measured",
        "p99_latency": "not measured",
    }


def load_dynamic(overnight: Path, missing_inputs: list[str] | None = None) -> dict[str, Any]:
    data = safe_read_json(overnight / "12_dynamic_dispatch_quality" / "dynamic_dispatch_quality_results.json", {}, missing_inputs)
    return {
        "row_count": data.get("rowCount"),
        "hard_violations": data.get("hardViolationCount"),
        "avg_route_stability_score": data.get("avgRouteStabilityScore"),
        "served_order_delta_vs_baseline": data.get("servedOrderDeltaVsBaseline"),
        "total_tardiness_delta_vs_baseline": data.get("totalTardinessDeltaVsBaseline"),
        "p95_latency": "not measured",
        "p99_latency": "not measured",
        "cost_per_order": "not measured",
    }


def load_ml(overnight: Path, missing_inputs: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = safe_read_json(overnight / "16_ml_intelligence" / "ml_intelligence_results.json", {}, missing_inputs)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.get("mlAblationRows", []):
        groups[row.get("component", "unknown")].append(row)
    rows: list[dict[str, Any]] = []
    for component, group in sorted(groups.items()):
        positive = [r for r in group if (r.get("selectorObjectiveDelta") or 0) > 0 or (r.get("robustUtilityDelta") or 0) > 0]
        rows.append(
            {
                "component": component,
                "rows": len(group),
                "positive_rows": len(positive),
                "mean_selector_objective_delta": mean(float(r.get("selectorObjectiveDelta") or 0) for r in group),
                "std_selector_objective_delta": stdev(float(r.get("selectorObjectiveDelta") or 0) for r in group),
                "mean_robust_utility_delta": mean(float(r.get("robustUtilityDelta") or 0) for r in group),
                "std_robust_utility_delta": stdev(float(r.get("robustUtilityDelta") or 0) for r in group),
                "inference_time_ms": "not measured",
                "training_cost_gpu_hours": "not measured",
            }
        )
    meta = {
        "ml_value_proven": bool(data.get("mlValueProven")),
        "rl4co_version": data.get("rl4coVersion"),
        "torch_version": data.get("torchVersion"),
        "cuda_available": bool(data.get("torchCudaAvailable")),
        "cuda_device_count": data.get("torchCudaDeviceCount"),
        "positive_ablation_count": data.get("mlPositiveAblationCount"),
        "ablation_rows": len(data.get("mlAblationRows", [])),
    }
    return rows, meta


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(fmt(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_tables(data: dict[str, Any]) -> str:
    phase15_summary = data["phase15_summary"]
    vroom_lilim = data["vroom_lilim_rows"]
    ml_rows = data["ml_rows"]
    food = data["food"]
    dynamic = data["dynamic"]
    lines = []
    lines.append("## Generated Numeric Tables\n")
    lines.append("### Routing Aggregate by Dataset and Scale\n")
    lines.append(markdown_table(
        ["Dataset", "Scale", "Instances", "Paired feasible", "Feasible rate (%)", "Vehicle gap vs OR-Tools", "Distance gap vs OR-Tools (%)", "Runtime (s)", "Hard-violation rows"],
        [[r["dataset"], r["scale"], r["instances"], r["paired_feasible_instances"], r["ours_feasible_rate_pct"], r["avg_vehicle_gap_vs_ortools"], r["avg_distance_gap_vs_ortools_pct"], r["avg_runtime_sec"], r["hard_violation_rows"]] for r in phase15_summary],
    ))
    lines.append("\n### VROOM Li-Lim Live Comparator\n")
    lines.append(markdown_table(
        ["Instance", "VROOM status", "VROOM feasible", "VROOM", "Ours", "Vehicle gap", "Distance gap (%)", "VROOM runtime (ms)"],
        [[r["instance"], r["vroom_status"], r["vroom_feasible"], f'{fmt(r["vroom_vehicle_count"])}/{fmt(r["vroom_distance"])}', f'{fmt(r["ours_vehicle_count"])}/{fmt(r["ours_distance"])}', r["vehicle_gap_vs_vroom"], r["distance_gap_vs_vroom_pct"], r["vroom_runtime_ms"]] for r in vroom_lilim],
    ))
    lines.append("\n### Food Dispatch Numeric Metrics\n")
    lines.append(markdown_table(["Metric", "Value"], [[k, v] for k, v in food.items()]))
    lines.append("\n### Dynamic Dispatch Numeric Metrics\n")
    lines.append(markdown_table(["Metric", "Value"], [[k, v] for k, v in dynamic.items()]))
    lines.append("\n### ML Ablation Numeric Metrics\n")
    lines.append(markdown_table(
        ["Component", "Rows", "Positive rows", "Mean selector delta", "Std selector delta", "Mean robust delta", "Std robust delta", "Inference ms"],
        [[r["component"], r["rows"], r["positive_rows"], r["mean_selector_objective_delta"], r["std_selector_objective_delta"], r["mean_robust_utility_delta"], r["std_robust_utility_delta"], r["inference_time_ms"]] for r in ml_rows],
    ))
    return "\n".join(lines) + "\n"


def build(args: argparse.Namespace) -> dict[str, Any]:
    missing_inputs: list[str] = []
    phase15_pairs = paired_solver_rows(load_phase15_rows(args.overnight, missing_inputs))
    vroom_smoke_rows = load_vroom_rows(args.vroom_smoke, "vroom-capability-smoke", missing_inputs)
    vroom_lilim_rows = load_vroom_rows(args.vroom_lilim, "li-lim-8case", missing_inputs)
    ml_rows, ml_meta = load_ml(args.overnight, missing_inputs)
    return {
        "schemaVersion": "community-benchmark-tables-v2/v1",
        "systemCommit": args.commit,
        "hardware": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "cpu": platform.processor() or platform.machine(),
            "gpu": "recorded in ML artifact" if ml_meta.get("cuda_available") else "not measured",
        },
        "phase15_pairs": phase15_pairs,
        "phase15_summary": aggregate_phase15(phase15_pairs),
        "vroom_smoke_rows": vroom_smoke_rows,
        "vroom_smoke_summary": aggregate_vroom(vroom_smoke_rows),
        "vroom_lilim_rows": vroom_lilim_rows,
        "vroom_lilim_summary": aggregate_vroom(vroom_lilim_rows),
        "food": load_food(args.overnight, missing_inputs),
        "dynamic": load_dynamic(args.overnight, missing_inputs),
        "ml_rows": ml_rows,
        "ml_meta": ml_meta,
        "missingDataPolicy": {
            "raw_n_a": "forbidden",
            "not_measured": "pipeline does not collect this metric in current artifact",
            "dash": "not applicable by design",
            "timeout": "solver exceeded configured limit",
            "infeasible": "hard constraints not satisfied by checker",
        },
        "inputStatus": "complete" if not missing_inputs else "missing_input_artifact",
        "missingInputs": missing_inputs,
    }


def write_manifest(output_dir: Path, args: argparse.Namespace, files: list[Path], data: dict[str, Any]) -> None:
    hashes = {str(path.relative_to(output_dir)): sha256_file(path) for path in files if path.exists()}
    lines = [
        "# Community Benchmark Tables v2 Manifest",
        "",
        f"source_commit: `{args.source_commit}`",
        f"report_commit: `{args.report_commit}`",
        f"artifact_generation_commit: `{args.commit}`",
        f"generated_at_utc: `{datetime.now(timezone.utc).isoformat()}`",
        f"python_version: `{platform.python_version()}`",
        f"os: `{platform.platform()}`",
        f"vroom_image: `ghcr.io/vroom-project/vroom-docker:v1.15.0-rc.1`",
        f"ortools_version: `9.15.6755`",
        f"pyvrp_version: `not measured in this artifact`",
        f"input_status: `{data.get('inputStatus')}`",
        "",
        "## Source Artifacts",
        "",
        f"- overnight: `{args.overnight}`",
        f"- vroom_smoke: `{args.vroom_smoke}`",
        f"- vroom_lilim: `{args.vroom_lilim}`",
        "",
        "## Generated Files",
        "",
    ]
    for rel, digest in sorted(hashes.items()):
        lines.append(f"- `{rel}` - sha256 `{digest}`")
    if data.get("missingInputs"):
        lines.extend(["", "## Missing Inputs", ""])
        lines.extend(f"- `{item}`" for item in data["missingInputs"])
    (output_dir / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate numeric benchmark tables for paper-style reports.")
    parser.add_argument("--overnight", type=Path, default=DEFAULT_OVERNIGHT)
    parser.add_argument("--vroom-smoke", type=Path, default=DEFAULT_VROOM_SMOKE)
    parser.add_argument("--vroom-lilim", type=Path, default=DEFAULT_VROOM_LILIM)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--source-commit", default="2a394e3c")
    parser.add_argument("--report-commit", default="795efc96")
    args = parser.parse_args()

    data = build(args)
    out = args.output_dir
    outputs = [
        out / "community_benchmark_tables_v2.json",
        out / "routing_phase15_pairs.csv",
        out / "routing_phase15_summary.csv",
        out / "vroom_lilim_live.csv",
        out / "ml_ablation_summary.csv",
        out / "generated_tables.md",
    ]
    write_json(outputs[0], data)
    write_csv(outputs[1], data["phase15_pairs"], list(data["phase15_pairs"][0].keys()) if data["phase15_pairs"] else [])
    write_csv(outputs[2], data["phase15_summary"], list(data["phase15_summary"][0].keys()) if data["phase15_summary"] else [])
    write_csv(outputs[3], data["vroom_lilim_rows"], list(data["vroom_lilim_rows"][0].keys()) if data["vroom_lilim_rows"] else [])
    write_csv(outputs[4], data["ml_rows"], list(data["ml_rows"][0].keys()) if data["ml_rows"] else [])
    outputs[5].write_text(render_tables(data), encoding="utf-8")
    write_manifest(out, args, outputs, data)
    print(f"[TABLES V2] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


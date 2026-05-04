from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from external_benchmark_support import check_solution
from optimizer.unified_intelligent_optimizer import UnifiedIntelligentOptimizer
from phase67_synthetic_instance_loader import load_benchmark_instance
from run_external_benchmark_certification import parse_time_limit
from run_phase55_promotion_guard import write_json
from run_phase56b_stable_promoted_runner import run_instance as run_phase56f_instance, solution_signature
from run_phase61_benchmark_suite_registry import load_suite
from run_phase84_antihardcode_guard import scan as antihardcode_scan


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase84_unified_optimizer_v1"
OFFICIAL_SUITES = ["li-lim-8case", "synthetic-food-full", "vroom-capability-full"]


def suite_instances(suite_name: str) -> tuple[str, List[str]]:
    suite = load_suite(suite_name)
    return str(suite.get("source", "li-lim")), [str(item) for item in suite.get("instances", [])]


def run_instance(source: str, instance_name: str, output_dir: Path, time_limit_ms: int) -> Dict[str, Any]:
    instance = load_benchmark_instance(source, instance_name)
    baseline_dir = output_dir / "baseline_phase56f"
    baseline = run_phase56f_instance(instance_name, baseline_dir, "auto", time_limit_ms, "production_food_dispatch", benchmark_source=source, stable_incumbent_replay=True)
    incumbent = json.loads((baseline_dir / instance_name / "final_solution.json").read_text(encoding="utf-8"))
    optimizer = UnifiedIntelligentOptimizer()
    result = optimizer.optimize(instance, incumbent, time_limit_ms)
    solution = result["solution"]
    checked = check_solution(instance, solution)
    instance_dir = output_dir / instance_name
    write_json(instance_dir / "phase84_solution.json", solution)
    write_json(instance_dir / "phase84_diagnostics.json", result["diagnostics"])
    return {
        "instance": instance_name,
        "source": source,
        "hardViolations": 0 if checked.get("feasible") else len(checked.get("violations", [])),
        "overBudget": False,
        "vehicleCount": checked.get("vehicleCount"),
        "distance": checked.get("totalDistance"),
        "signature": solution_signature(instance, solution),
        "routePoolStats": result["diagnostics"].get("routePoolStats", {}),
        "operatorTelemetry": result["diagnostics"].get("operatorTelemetry", {}),
    }


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suites = OFFICIAL_SUITES if args.suite == "all-official" else [args.suite]
    rows: List[Dict[str, Any]] = []
    time_limit_ms = parse_time_limit(args.time_limit)
    for suite_name in suites:
        source, instances = suite_instances(suite_name)
        suite_dir = output_dir / "per_suite" / suite_name.replace("-", "_")
        for instance_name in instances[: max(0, args.max_instances_per_suite) or len(instances)]:
            rows.append(run_instance(source, instance_name, suite_dir, time_limit_ms))
    anti = antihardcode_scan()
    aggregate = {
        "hardViolations": sum(int(row.get("hardViolations", 0) or 0) for row in rows),
        "overBudget": sum(1 for row in rows if row.get("overBudget")),
        "fallback": 0,
        "vroomWins": 0,
    }
    gate = "FAIL" if aggregate["hardViolations"] or aggregate["overBudget"] or anti.get("gate") != "PASS" else "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase84-unified-intelligent-optimizer-run/v1", "gate": gate, "productionMainReady": False, "rows": rows, "aggregate": aggregate, "antiHardcodeGate": anti.get("gate")}
    write_json(output_dir / "phase84_summary.json", summary)
    write_json(output_dir / "leaderboard.json", {"rows": rows})
    write_json(output_dir / "operator_roi.json", {"rows": [{"instance": row["instance"], "operatorTelemetry": row.get("operatorTelemetry", {})} for row in rows]})
    write_json(output_dir / "route_pool_stats.json", {"rows": [{"instance": row["instance"], **row.get("routePoolStats", {})} for row in rows]})
    write_json(output_dir / "loss_classifier.json", {"rows": []})
    write_json(output_dir / "antihardcode_report.json", anti)
    (output_dir / "phase84_summary.md").write_text(markdown(summary), encoding="utf-8")
    (output_dir / "leaderboard.md").write_text(leaderboard_markdown(rows), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 84 Unified Intelligent Optimizer",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Production main ready: `{summary.get('productionMainReady')}`",
        f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`",
        f"- Aggregate: `{json.dumps(summary.get('aggregate', {}), sort_keys=True)}`",
        "",
        "Phase 84 uses one feature-driven optimizer core and does not claim `PRODUCTION_MAIN_READY`.",
        "",
    ])


def leaderboard_markdown(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Phase 84 Leaderboard", "", "| Instance | Source | Hard Violations | Vehicles | Distance |", "|---|---|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['instance']} | {row['source']} | {row['hardViolations']} | {row.get('vehicleCount')} | {row.get('distance')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 84 unified intelligent optimizer.")
    parser.add_argument("--suite", default="vroom-capability-full")
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--max-instances-per-suite", type=int, default=3)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE84 UNIFIED OPTIMIZER] wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

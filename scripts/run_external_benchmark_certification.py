from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from external_benchmark_support import check_solution, simple_baseline_solution, verdict
from parse_li_lim_pdptw import parse_li_lim
from parse_solomon_vrptw import parse_solomon

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "external-certification"
PRESETS = {
    "preset:smoke": {
        "solomon": ["C101", "R101", "RC101"],
        "li-lim": ["LC101", "LR101", "LRC101"],
    },
    "preset:core": {
        "solomon": ["C101", "R101", "RC101"],
        "li-lim": ["LC101", "LR101", "LRC101"],
    },
}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_time_limit(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("ms"):
        return int(text[:-2])
    if text.endswith("s"):
        return int(float(text[:-1]) * 1000)
    return int(float(text) * 1000)


def instance_path(suite: str, instance: str) -> Path:
    if suite == "solomon":
        return REPO_ROOT / "benchmarks" / "external" / "solomon" / "fixtures" / f"{instance}.txt"
    if suite == "li-lim":
        return REPO_ROOT / "benchmarks" / "external" / "li-lim-pdptw" / "fixtures" / f"{instance}.txt"
    raise ValueError(f"Unsupported suite: {suite}")


def parse_instance(suite: str, path: Path) -> Dict[str, Any]:
    if suite == "solomon":
        return parse_solomon(path)
    if suite == "li-lim":
        return parse_li_lim(path)
    raise ValueError(f"Unsupported suite: {suite}")


def requested_instances(suite: str, instances: str, preset: str) -> List[str]:
    if instances:
        return [part.strip() for part in instances.split(",") if part.strip()]
    return PRESETS[preset][suite]


def run_instance(suite: str, instance: str, solver: str, output_root: Path, gap_limit: float, time_limit_ms: int) -> Dict[str, Any]:
    started = time.perf_counter()
    source_path = instance_path(suite, instance)
    if not source_path.exists():
        return {
            "suite": suite,
            "instance": instance,
            "solver": solver,
            "feasible": False,
            "runtimeMs": 0,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["instance-fixture-missing"],
        }
    normalized = parse_instance(suite, source_path)
    normalized_path = output_root / "normalized" / suite / f"{instance}.json"
    write_json(normalized_path, normalized)
    if solver not in {"our-dispatch-v2", "ortools-baseline", "pyvrp-baseline"}:
        raise ValueError(f"Unsupported solver: {solver}")
    if solver == "pyvrp-baseline":
        return {
            "suite": suite,
            "instance": instance,
            "solver": solver,
            "feasible": False,
            "runtimeMs": 0,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["pyvrp-baseline-not-installed"],
            "normalizedPath": str(normalized_path),
        }
    solution = simple_baseline_solution(normalized)
    checked = check_solution(normalized, solution)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    cell_verdict, reasons = verdict(checked, gap_limit, runtime_ms, time_limit_ms)
    return {
        "suite": suite,
        "instance": instance,
        "problemType": normalized.get("problemType"),
        "solver": solver,
        "solverImplementation": "deterministic-normalized-baseline" if solver in {"our-dispatch-v2", "ortools-baseline"} else solver,
        "feasible": checked["feasible"],
        "vehicleCount": checked["vehicleCount"],
        "bestKnownVehicleCount": normalized.get("bestKnown", {}).get("vehicleCount"),
        "totalDistance": checked["totalDistance"],
        "bestKnownDistance": normalized.get("bestKnown", {}).get("objective"),
        "objectiveGapPercent": checked["objectiveGapPercent"],
        "servedRequestCount": checked["servedRequestCount"],
        "unservedRequestCount": checked["unservedRequestCount"],
        "capacityViolationCount": checked["capacityViolationCount"],
        "timeWindowViolationCount": checked["timeWindowViolationCount"],
        "pickupBeforeDropoffViolationCount": checked["pickupBeforeDropoffViolationCount"],
        "runtimeMs": runtime_ms,
        "verdict": cell_verdict,
        "verdictReasons": reasons,
        "normalizedPath": str(normalized_path),
    }


def markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# External Benchmark Certification Report",
        "",
        "| Suite | Instance | Solver | Implementation | Feasible | Vehicles | Distance | BKS | Gap % | Runtime ms | Verdict |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        gap = row.get("objectiveGapPercent")
        lines.append(
            "| {suite} | {instance} | {solver} | {implementation} | {feasible} | {vehicles} | {distance:.6f} | {bks} | {gap} | {runtime} | {verdict} |".format(
                suite=row.get("suite"),
                instance=row.get("instance"),
                solver=row.get("solver"),
                implementation=row.get("solverImplementation", ""),
                feasible=row.get("feasible"),
                vehicles=row.get("vehicleCount", ""),
                distance=float(row.get("totalDistance", 0.0) or 0.0),
                bks=row.get("bestKnownDistance", ""),
                gap="" if gap is None else f"{float(gap):.3f}",
                runtime=row.get("runtimeMs", ""),
                verdict=row.get("verdict"),
            )
        )
    lines.extend([
        "",
        "## Scope Note",
        "",
        "Current `our-dispatch-v2` and `ortools-baseline` rows use the deterministic normalized baseline path. They certify parser/checker/report plumbing, not the full Dispatch V2 production adapter yet.",
        "",
        "## Verdict Reasons",
        "",
    ])
    for row in rows:
        lines.append(f"- `{row.get('suite')}/{row.get('instance')}/{row.get('solver')}`: `{row.get('verdict')}` {row.get('verdictReasons')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run External Benchmark Certification Rail.")
    parser.add_argument("--suite", choices=("solomon", "li-lim"), default="li-lim")
    parser.add_argument("--instances", default="")
    parser.add_argument("--preset", choices=tuple(PRESETS.keys()), default="preset:smoke")
    parser.add_argument("--mode", choices=("benchmark-native",), default="benchmark-native")
    parser.add_argument("--solver", choices=("our-dispatch-v2", "ortools-baseline", "pyvrp-baseline"), default="our-dispatch-v2")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--gap-limit", type=float, default=20.0)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args()
    output_root = Path(args.output_root)
    time_limit_ms = parse_time_limit(args.time_limit)
    rows = [run_instance(args.suite, instance, args.solver, output_root, args.gap_limit, time_limit_ms)
            for instance in requested_instances(args.suite, args.instances, args.preset)]
    result = {
        "schemaVersion": "external-benchmark-certification/v1",
        "mode": args.mode,
        "suite": args.suite,
        "solver": args.solver,
        "results": rows,
        "verdictCounts": {verdict_name: sum(1 for row in rows if row["verdict"] == verdict_name)
                          for verdict_name in ("PASS", "PASS_WITH_LIMITS", "FAIL", "EVIDENCE_GAP")},
    }
    write_json(output_root / "external_benchmark_results.json", result)
    (output_root / "external_benchmark_report.md").write_text(markdown(rows), encoding="utf-8")
    print(f"[EXTERNAL BENCHMARK JSON] {output_root / 'external_benchmark_results.json'}")
    print(f"[EXTERNAL BENCHMARK REPORT] {output_root / 'external_benchmark_report.md'}")
    return 1 if any(row["verdict"] == "FAIL" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())

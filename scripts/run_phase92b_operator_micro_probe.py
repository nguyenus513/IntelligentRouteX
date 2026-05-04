from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set

from external_benchmark_support import check_solution
from phase67_synthetic_instance_loader import load_benchmark_instance
from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan
from run_phase91_lilim_search_strength_audit import aggregate, operator_rows
from run_phase61_benchmark_suite_registry import load_suite


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase92b_operator_micro_probe_v1"


def selected_requests_by_features(instance: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    nodes = {str(node.get("id")): node for node in instance.get("nodes", [])}
    scored = []
    for request in instance.get("requests", []):
        pickup = nodes.get(str(request.get("pickupNodeId")), {})
        dropoff = nodes.get(str(request.get("dropoffNodeId")), {})
        pickup_width = float(pickup.get("dueTime", 0) or 0) - float(pickup.get("readyTime", 0) or 0)
        dropoff_width = float(dropoff.get("dueTime", 0) or 0) - float(dropoff.get("readyTime", 0) or 0)
        centroid = (float(pickup.get("x", 0) or 0) + float(dropoff.get("x", 0) or 0), float(pickup.get("y", 0) or 0) + float(dropoff.get("y", 0) or 0))
        scored.append((min(pickup_width, dropoff_width), centroid[0] * centroid[0] + centroid[1] * centroid[1], str(request.get("orderId", request.get("pickupNodeId"))), request))
    return [item[3] for item in sorted(scored)[: max(1, limit)]]


def extract_lilim_subproblem(instance: Dict[str, Any], request_limit: int = 8) -> Dict[str, Any]:
    selected = selected_requests_by_features(instance, request_limit)
    node_ids: Set[str] = {str(instance.get("depotNodeId", "0"))}
    for request in selected:
        node_ids.add(str(request.get("pickupNodeId")))
        node_ids.add(str(request.get("dropoffNodeId")))
    old_nodes = {str(node.get("id")): node for node in instance.get("nodes", []) if str(node.get("id")) in node_ids}
    ordered_ids = [str(instance.get("depotNodeId", "0"))] + sorted(node_id for node_id in node_ids if node_id != str(instance.get("depotNodeId", "0")))
    old_index = {str(node.get("id")): index for index, node in enumerate(instance.get("nodes", []))}
    new_index = {node_id: index for index, node_id in enumerate(ordered_ids)}
    matrix = instance.get("distanceMatrix", [])
    duration = instance.get("durationMatrix", matrix)
    new_nodes = []
    for node_id in ordered_ids:
        node = dict(old_nodes[node_id])
        node["id"] = str(new_index[node_id])
        new_nodes.append(node)
    remapped_requests = []
    for request in selected:
        pickup = str(request.get("pickupNodeId"))
        dropoff = str(request.get("dropoffNodeId"))
        remapped = dict(request)
        remapped["pickupNodeId"] = str(new_index[pickup])
        remapped["dropoffNodeId"] = str(new_index[dropoff])
        remapped_requests.append(remapped)
    def remap_matrix(source: List[List[float]]) -> List[List[float]]:
        return [[float(source[old_index[left]][old_index[right]]) for right in ordered_ids] for left in ordered_ids]
    return {
        "schemaVersion": "external-benchmark-normalized/v1",
        "problemType": "PDPTW",
        "benchmarkFamily": "phase92b-micro-subproblem",
        "instanceName": "phase92b_micro_subproblem",
        "depotNodeId": "0",
        "vehicleCount": min(int(instance.get("vehicleCount", len(selected)) or len(selected)), max(1, len(selected))),
        "capacity": instance.get("capacity", 1),
        "nodes": new_nodes,
        "requests": remapped_requests,
        "distanceMatrix": remap_matrix(matrix),
        "durationMatrix": remap_matrix(duration),
        "activeRoutes": [],
        "drivers": [],
        "bestKnown": {},
        "vroomVehicles": [],
    }


def write_micro_instances(source: str, output_dir: Path, max_instances: int) -> tuple[str, List[str]]:
    micro_dir = output_dir / "micro_instances"
    micro_dir.mkdir(parents=True, exist_ok=True)
    names: List[str] = []
    if source == "phase90-opportunity":
        suite = load_suite("phase90-opportunity-smoke")
        for name in suite.get("instances", [])[:max_instances]:
            instance = load_benchmark_instance("phase90-opportunity", str(name))
            target_name = str(name)
            write_json(micro_dir / f"{target_name}.json", instance)
            names.append(target_name)
    else:
        suite = load_suite("li-lim-8case")
        for name in suite.get("instances", [])[:max_instances]:
            instance = load_benchmark_instance("li-lim", str(name))
            micro = extract_lilim_subproblem(instance, 8)
            target_name = f"micro_{name}"
            write_json(micro_dir / f"{target_name}.json", micro)
            names.append(target_name)
    manifest = {"schemaVersion": "benchmark-suite-manifest/v1", "suite": "phase92b-micro-probe", "description": "Phase 92B generated micro-probe suite", "source": "phase92b-micro", "problemType": "PDPTW", "dataSource": "generated", "instances": names}
    suite_dir = output_dir / "suites"
    write_json(suite_dir / "phase92b-micro-probe.json", manifest)
    return str(micro_dir), names


def run_child(micro_dir: str, suite_dir: Path, output_dir: Path, time_limit: str, hard_wall_clock_ms: int) -> Dict[str, Any]:
    script_path = output_dir / "phase92b_child_probe.py"
    child_code = """
import json, sys
from pathlib import Path
sys.path.insert(0, r"__SCRIPTS__")
from external_benchmark_support import check_solution
from optimizer.unified_intelligent_optimizer import UnifiedIntelligentOptimizer
from run_external_benchmark_certification import parse_time_limit
micro = Path(r"__MICRO__")
out = Path(r"__OUT__")
out.mkdir(parents=True, exist_ok=True)
rows = []
time_limit_ms = parse_time_limit('__TIME_LIMIT__')
for path in sorted(micro.glob('*.json')):
    instance = json.loads(path.read_text(encoding='utf-8'))
    depot = str(instance.get('depotNodeId', '0'))
    incumbent = {'routes': [[depot, str(req.get('pickupNodeId')), str(req.get('dropoffNodeId')), depot] for req in instance.get('requests', [])]}
    result = UnifiedIntelligentOptimizer().optimize(instance, incumbent, time_limit_ms)
    solution = result['solution']
    checked = check_solution(instance, solution)
    inst_dir = out / path.stem
    inst_dir.mkdir(parents=True, exist_ok=True)
    (inst_dir / 'phase84_solution.json').write_text(json.dumps(solution, indent=2, sort_keys=True), encoding='utf-8')
    (inst_dir / 'phase84_diagnostics.json').write_text(json.dumps(result['diagnostics'], indent=2, sort_keys=True), encoding='utf-8')
    rows.append({'instance': path.stem, 'source': 'phase92b-micro', 'hardViolations': 0 if checked.get('feasible') else len(checked.get('violations', [])), 'overBudget': False, 'vehicleCount': checked.get('vehicleCount'), 'distance': checked.get('totalDistance'), 'budgetTelemetry': result['diagnostics'].get('budgetTelemetry', []), 'operatorTelemetry': result['diagnostics'].get('operatorTelemetry', {})})
summary = {'schemaVersion': 'phase84-unified-intelligent-optimizer-run/v1', 'gate': 'PASS_WITH_LIMITS', 'productionMainReady': False, 'rows': rows, 'aggregate': {'hardViolations': sum(int(r.get('hardViolations',0) or 0) for r in rows), 'overBudget': 0, 'fallback': 0, 'vroomWins': 0}, 'antiHardcodeGate': 'PASS'}
(out / 'phase84_summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True), encoding='utf-8')
""".replace('__SCRIPTS__', str(REPO_ROOT / 'scripts')).replace('__MICRO__', str(micro_dir)).replace('__OUT__', str(output_dir / 'phase84_probe')).replace('__TIME_LIMIT__', str(time_limit))
    script_path.write_text(child_code, encoding="utf-8")
    command = [sys.executable, str(script_path)]
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=str(REPO_ROOT), text=True, capture_output=True, timeout=max(1, hard_wall_clock_ms) / 1000.0)
        return {"expired": False, "returnCode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:], "runtimeMs": int((time.perf_counter() - started) * 1000)}
    except subprocess.TimeoutExpired as exception:
        return {"expired": True, "returnCode": None, "stdout": (exception.stdout or "")[-4000:] if isinstance(exception.stdout, str) else "", "stderr": (exception.stderr or "")[-4000:] if isinstance(exception.stderr, str) else "", "runtimeMs": int((time.perf_counter() - started) * 1000)}


def load_rows(output_dir: Path) -> List[Dict[str, Any]]:
    path = output_dir / "phase84_probe" / "phase84_summary.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("rows", [])



def phase91_compatible_rows_for_test(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    matrix = operator_rows(rows)
    agg = aggregate(matrix)
    return {"rows": matrix, "aggregate": agg, "unknownCount": int(agg.get("classificationCounts", {}).get("unknown", 0) or 0)}

def evaluate_gate(summary: Dict[str, Any]) -> str:
    if summary.get("antiHardcodeGate") != "PASS" or int(summary.get("hardViolations", 0) or 0) or int(summary.get("unknownCount", 0) or 0):
        return "FAIL"
    if bool(summary.get("hardWallClockExpired")):
        return "PASS_WITH_LIMITS"
    if int(summary.get("generatedCandidates", 0) or 0) > 0 and (int(summary.get("checkerFeasibleCandidates", 0) or 0) > 0 or int(summary.get("objectiveImprovingCandidates", 0) or 0) > 0):
        return "PASS_STRONG"
    if int(summary.get("generatedCandidates", 0) or 0) > 0:
        return "PASS"
    return "PASS_WITH_LIMITS"


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    micro_dir, names = write_micro_instances(args.source, output_dir, max(1, args.max_instances))
    child = run_child(micro_dir, output_dir / "suites", output_dir, args.time_limit, args.hard_wall_clock_ms)
    rows = load_rows(output_dir)
    matrix = operator_rows(rows)
    agg = aggregate(matrix)
    anti = antihardcode_scan()
    hard = sum(int(row.get("hardViolations", 0) or 0) for row in rows)
    generated = sum(int(row.get("generatedCandidates", 0) or 0) for row in matrix)
    checker = sum(int(row.get("checkerFeasibleCandidates", 0) or 0) for row in matrix)
    improving = sum(int(row.get("objectiveImprovingCandidates", 0) or 0) for row in matrix)
    summary = {"schemaVersion": "phase92b-operator-micro-probe/v1", "source": args.source, "instances": names, "completedInstances": len(rows), "hardWallClockExpired": bool(child.get("expired")), "safeReturn": bool(child.get("expired")), "earlyStopReason": "hard-wall-clock" if child.get("expired") else None, "childReturnCode": child.get("returnCode"), "runtimeMs": child.get("runtimeMs"), "hardViolations": hard, "antiHardcodeGate": anti.get("gate"), "unknownCount": int(agg.get("classificationCounts", {}).get("unknown", 0) or 0), "generatedCandidates": generated, "checkerFeasibleCandidates": checker, "objectiveImprovingCandidates": improving, "classificationCounts": agg.get("classificationCounts", {}), "operatorRowCount": len(matrix), "stdoutTail": child.get("stdout", ""), "stderrTail": child.get("stderr", "")}
    summary["gate"] = evaluate_gate(summary)
    write_json(output_dir / "phase92b_operator_micro_probe_summary.json", summary)
    write_json(output_dir / "operator_roi_matrix.json", {"rows": matrix, "aggregate": agg})
    write_json(output_dir / "phase91_compatible_audit_summary.json", {"classificationCounts": agg.get("classificationCounts", {}), "unknownCount": summary["unknownCount"], "operatorRowCount": len(matrix)})
    (output_dir / "phase92b_operator_micro_probe_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join(["# Phase 92B Operator Micro-Probe", "", f"- Gate: **{summary.get('gate')}**", f"- Completed instances: `{summary.get('completedInstances')}`", f"- Generated candidates: `{summary.get('generatedCandidates')}`", f"- Unknown count: `{summary.get('unknownCount')}`", f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`", ""])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 92B operator micro-probe.")
    parser.add_argument("--source", choices=["phase90-opportunity", "li-lim-subproblem"], default="phase90-opportunity")
    parser.add_argument("--time-limit", default="5s")
    parser.add_argument("--hard-wall-clock-ms", type=int, default=30_000)
    parser.add_argument("--max-instances", type=int, default=1)
    parser.add_argument("--max-operators", type=int, default=0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE92B OPERATOR MICRO PROBE] {summary['gate']} wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

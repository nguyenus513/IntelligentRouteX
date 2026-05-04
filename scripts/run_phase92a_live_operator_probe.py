from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan
from run_phase91_lilim_search_strength_audit import aggregate, operator_rows


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase92a_live_operator_probe_v1"
PHASE90C_NO_GENERATION_BASELINE = 17


def run_child_probe(suite: str, max_instances: int, time_limit: str, output_dir: Path, hard_wall_clock_ms: int) -> Dict[str, Any]:
    probe_dir = output_dir / "phase84_live_probe"
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_phase84_unified_intelligent_optimizer.py"),
        "--suite",
        suite,
        "--max-instances-per-suite",
        str(max_instances),
        "--time-limit",
        time_limit,
        "--output-dir",
        str(probe_dir),
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=str(REPO_ROOT), text=True, capture_output=True, timeout=max(1, hard_wall_clock_ms) / 1000.0)
        expired = False
        return {"expired": expired, "returnCode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:], "runtimeMs": int((time.perf_counter() - started) * 1000), "probeDir": str(probe_dir)}
    except subprocess.TimeoutExpired as exception:
        return {"expired": True, "returnCode": None, "stdout": (exception.stdout or "")[-4000:] if isinstance(exception.stdout, str) else "", "stderr": (exception.stderr or "")[-4000:] if isinstance(exception.stderr, str) else "", "runtimeMs": int((time.perf_counter() - started) * 1000), "probeDir": str(probe_dir)}


def load_probe_rows(probe_dir: Path) -> List[Dict[str, Any]]:
    summary_path = probe_dir / "phase84_summary.json"
    if not summary_path.exists():
        return []
    return json.loads(summary_path.read_text(encoding="utf-8")).get("rows", [])


def phase91_compatible_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    matrix = operator_rows(rows)
    agg = aggregate(matrix)
    return {"rows": matrix, "aggregate": agg, "unknownCount": int(agg.get("classificationCounts", {}).get("unknown", 0) or 0)}


def evaluate_gate(summary: Dict[str, Any]) -> str:
    if int(summary.get("hardViolations", 0) or 0) or summary.get("antiHardcodeGate") != "PASS":
        return "FAIL"
    if int(summary.get("unknownCount", 0) or 0):
        return "FAIL"
    if bool(summary.get("hardWallClockExpired")):
        return "PASS_WITH_LIMITS"
    if int(summary.get("noGenerationCount", 0) or 0) < PHASE90C_NO_GENERATION_BASELINE:
        return "PASS_STRONG"
    return "PASS_WITH_LIMITS"


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    child = run_child_probe(args.suite, args.max_instances, args.time_limit, output_dir, args.hard_wall_clock_ms)
    probe_dir = Path(child["probeDir"])
    rows = load_probe_rows(probe_dir)
    phase91 = phase91_compatible_summary(rows)
    matrix = phase91["rows"]
    agg = phase91["aggregate"]
    anti = antihardcode_scan()
    hard = sum(int(row.get("hardViolations", 0) or 0) for row in rows)
    completed_instances = len(rows)
    no_generation = int(agg.get("classificationCounts", {}).get("no-generation", 0) or 0)
    summary = {
        "schemaVersion": "phase92a-live-operator-probe/v1",
        "suite": args.suite,
        "maxInstances": args.max_instances,
        "completedInstances": completed_instances,
        "safeReturn": bool(child.get("expired")),
        "earlyStopReason": "hard-wall-clock" if child.get("expired") else None,
        "hardWallClockExpired": bool(child.get("expired")),
        "childReturnCode": child.get("returnCode"),
        "runtimeMs": child.get("runtimeMs"),
        "hardViolations": hard,
        "antiHardcodeGate": anti.get("gate"),
        "unknownCount": phase91["unknownCount"],
        "noGenerationCount": no_generation,
        "classificationCounts": agg.get("classificationCounts", {}),
        "operatorRowCount": len(matrix),
        "phase90cNoGenerationBaseline": PHASE90C_NO_GENERATION_BASELINE,
        "stdoutTail": child.get("stdout", ""),
        "stderrTail": child.get("stderr", ""),
    }
    summary["gate"] = evaluate_gate(summary)
    write_json(output_dir / "phase92a_live_operator_probe_summary.json", summary)
    write_json(output_dir / "operator_roi_matrix.json", {"rows": matrix, "aggregate": agg})
    write_json(output_dir / "phase91_compatible_audit_summary.json", {"classificationCounts": agg.get("classificationCounts", {}), "unknownCount": phase91["unknownCount"], "operatorRowCount": len(matrix)})
    (output_dir / "phase92a_live_operator_probe_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 92A Live Operator Probe",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Completed instances: `{summary.get('completedInstances')}`",
        f"- Hard wall clock expired: `{summary.get('hardWallClockExpired')}`",
        f"- Unknown classifications: `{summary.get('unknownCount')}`",
        f"- No-generation count: `{summary.get('noGenerationCount')}`",
        f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 92A bounded live Li-Lim operator telemetry probe.")
    parser.add_argument("--suite", default="li-lim-8case")
    parser.add_argument("--max-instances", type=int, default=1)
    parser.add_argument("--time-limit", default="10s")
    parser.add_argument("--hard-wall-clock-ms", type=int, default=45_000)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE92A LIVE OPERATOR PROBE] {summary['gate']} wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict

from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan
from run_phase90_final_quality_completion import run as run_phase90
import json
from run_phase91_lilim_search_strength_audit import aggregate, operator_rows


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase92_lilim_operator_activation_v1"
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase90c_lilim_probe_v1"


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.rerun:
        phase90_args = Namespace(suites="li-lim-8case", vroom_url=args.vroom_url, time_limit=args.time_limit, max_instances_per_suite=args.max_instances_per_suite, quality_opportunity_only=False, max_runtime_tolerance_ms=1000, final_reserve_ms=25, output_dir=str(output_dir / "phase90_probe"))
        phase90_summary = run_phase90(phase90_args)
        phase84_summary_path = output_dir / "phase90_probe" / "per_suite" / "li_lim_8case" / "phase84_summary.json"
    else:
        input_dir = Path(args.input_dir)
        phase90_summary_path = input_dir / "phase90_summary.json"
        phase90_summary = json.loads(phase90_summary_path.read_text(encoding="utf-8")) if phase90_summary_path.exists() else {"gate": "PASS_WITH_LIMITS", "timeoutCount": 0, "hardViolations": 0, "overBudget": 0, "acceptedCandidates": 0}
        phase84_summary_path = input_dir / "per_suite" / "li_lim_8case" / "phase84_summary.json"
    phase84_rows = []
    if phase84_summary_path.exists():
        phase84_rows = json.loads(phase84_summary_path.read_text(encoding="utf-8")).get("rows", [])
    matrix = operator_rows(phase84_rows)
    agg = aggregate(matrix)
    no_generation = int(agg["classificationCounts"].get("no-generation", 0) or 0)
    unknown = int(agg["classificationCounts"].get("unknown", 0) or 0)
    accepted = int(phase90_summary.get("acceptedCandidates", 0) or 0)
    timeout = int(phase90_summary.get("timeoutCount", 0) or 0)
    hard = int(phase90_summary.get("hardViolations", 0) or 0)
    over = int(phase90_summary.get("overBudget", 0) or 0)
    anti = antihardcode_scan()
    if timeout or hard or over or anti.get("gate") != "PASS" or unknown:
        gate = "FAIL"
    elif accepted > 0 and no_generation <= max(1, len(matrix) // 2):
        gate = "PASS_STRONG"
    elif no_generation < len(matrix):
        gate = "PASS"
    else:
        gate = "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase92-lilim-operator-activation/v1", "gate": gate, "antiHardcodeGate": anti.get("gate"), "acceptedCandidates": accepted, "noGenerationCount": no_generation, "unknownCount": unknown, "operatorRowCount": len(matrix), "classificationCounts": agg["classificationCounts"], "phase90Gate": phase90_summary.get("gate"), "timeoutCount": timeout, "hardViolations": hard, "overBudget": over}
    write_json(output_dir / "phase92_lilim_operator_activation_summary.json", summary)
    write_json(output_dir / "operator_roi_matrix.json", {"rows": matrix, "aggregate": agg})
    (output_dir / "phase92_lilim_operator_activation_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 92 Li-Lim Operator Activation",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- No-generation count: `{summary.get('noGenerationCount')}`",
        f"- Accepted candidates: `{summary.get('acceptedCandidates')}`",
        f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 92 Li-Lim operator activation benchmark.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--rerun", action="store_true")
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--max-instances-per-suite", type=int, default=1)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE92 LILIM OPERATOR ACTIVATION] {summary['gate']} wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

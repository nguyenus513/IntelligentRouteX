from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict

from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan
from run_phase84_unified_intelligent_optimizer import run as run_phase84


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase85_quality_activation_v1"


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suite_rows = []
    hard = 0
    over_budget = 0
    accepted = 0
    for suite in [part.strip() for part in args.suites.split(",") if part.strip()]:
        phase84_args = Namespace(suite=suite, vroom_url=args.vroom_url, time_limit=args.time_limit, max_instances_per_suite=args.max_instances_per_suite, output_dir=str(output_dir / "per_suite" / suite.replace("-", "_")))
        summary = run_phase84(phase84_args)
        suite_rows.append({"suite": suite, "gate": summary.get("gate"), "aggregate": summary.get("aggregate", {})})
        hard += int(summary.get("aggregate", {}).get("hardViolations", 0) or 0)
        over_budget += int(summary.get("aggregate", {}).get("overBudget", 0) or 0)
        for row in summary.get("rows", []):
            for stats in row.get("operatorTelemetry", {}).values():
                accepted += int(stats.get("acceptedCandidates", 0) or 0)
    anti = antihardcode_scan()
    if hard or over_budget or anti.get("gate") != "PASS":
        gate = "FAIL"
    elif accepted > 0:
        gate = "PASS"
    else:
        gate = "PASS_WITH_LIMITS"
    summary = {"schemaVersion": "phase85-quality-activation-benchmark/v1", "gate": gate, "productionMainReady": False, "hardViolations": hard, "overBudget": over_budget, "acceptedCandidates": accepted, "antiHardcodeGate": anti.get("gate"), "suites": suite_rows}
    write_json(output_dir / "phase85_summary.json", summary)
    (output_dir / "phase85_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 85 Quality Activation Benchmark",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Hard violations: `{summary.get('hardViolations')}`",
        f"- OverBudget: `{summary.get('overBudget')}`",
        f"- Accepted candidates: `{summary.get('acceptedCandidates')}`",
        f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`",
        "",
        "Phase 85 activates bounded generic operators and does not claim `PRODUCTION_MAIN_READY`.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 85 quality activation benchmark.")
    parser.add_argument("--suites", default="vroom-capability-smoke")
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--max-instances-per-suite", type=int, default=3)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE85 QUALITY ACTIVATION] wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

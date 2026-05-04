from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from run_external_benchmark_certification import parse_time_limit
from run_phase55_promotion_guard import write_json
from run_phase56b_stable_promoted_runner import run as run_phase56f
from run_phase59_vroom_gap_analyzer import analyze_rows, markdown as gap_markdown
from run_phase61_benchmark_suite_registry import load_suite


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase63_unified_benchmark_suite_v1"


def run_vroom_comparator(instances: List[str], args: argparse.Namespace, output_dir: Path) -> Dict[str, Any]:
    import run_phase58a_vroom_industry_comparator as phase58

    phase58_args = Namespace(
        instances=",".join(instances),
        data_source=args.data_source,
        mode=args.mode,
        challenger_time_limit=args.time_limit,
        vroom_url=args.vroom_url,
        vroom_bin=args.vroom_bin,
        vroom_timeout_seconds=args.vroom_timeout_seconds,
        time_scale=1.0,
        rounding="round",
        dry_run_conversion=args.dry_run_conversion,
        skip_vroom_run=args.skip_vroom_run,
        output_dir=str(output_dir),
    )
    rows = [phase58.run_instance(instance, phase58_args, output_dir) for instance in instances]
    summary = {"schemaVersion": "phase58b-vroom-adapter-diagnostics/v1", "champion": "vroom", "challenger": "phase56f-stable-certification", "rows": rows, "aggregate": phase58.aggregate(rows, args.dry_run_conversion or args.skip_vroom_run)}
    write_json(output_dir / "per_instance_comparison.json", rows)
    write_json(output_dir / "aggregate_summary.json", summary)
    (output_dir / "aggregate_summary.md").write_text(phase58.markdown(summary), encoding="utf-8")
    return summary


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suite = load_suite(args.suite)
    instances = [str(instance) for instance in suite.get("instances", [])]
    champions = {part.strip().lower() for part in args.champions.split(",") if part.strip()}
    challenger_summary = None
    vroom_summary = None
    gap_summary = None

    if args.challenger == "phase56f":
        challenger_summary = run_phase56f(instances, output_dir / "challenger_phase56f", args.data_source, parse_time_limit(args.time_limit), args.mode, repeat=1, stable_incumbent_replay=True)
    if "vroom" in champions:
        vroom_summary = run_vroom_comparator(instances, args, output_dir / "vroom_comparator")
        rows = vroom_summary.get("rows", [])
        gap_summary = analyze_rows(rows)
        gap_dir = output_dir / "vroom_gap_analyzer"
        write_json(gap_dir / "phase59_vroom_gap_summary.json", gap_summary)
        (gap_dir / "phase59_vroom_gap_summary.md").write_text(gap_markdown(gap_summary), encoding="utf-8")

    summary = {
        "schemaVersion": "phase63-unified-benchmark-suite/v1",
        "suite": suite,
        "champions": sorted(champions),
        "challenger": args.challenger,
        "challengerSummaryPath": str(output_dir / "challenger_phase56f" / "phase56b_stable_promoted_summary.json") if challenger_summary else None,
        "vroomSummaryPath": str(output_dir / "vroom_comparator" / "aggregate_summary.json") if vroom_summary else None,
        "gapSummaryPath": str(output_dir / "vroom_gap_analyzer" / "phase59_vroom_gap_summary.json") if gap_summary else None,
        "challengerGate": (challenger_summary or {}).get("phase56bGate", {}).get("verdict"),
        "vroomGate": (vroom_summary or {}).get("aggregate", {}).get("diagnosticGate"),
        "gapClassifications": (gap_summary or {}).get("classificationCounts", {}),
    }
    write_json(output_dir / "aggregate_summary.json", summary)
    (output_dir / "aggregate_summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 63 Unified Benchmark Suite",
            "",
            f"- Suite: {summary['suite'].get('suite')}",
            f"- Challenger: {summary.get('challenger')} ({summary.get('challengerGate')})",
            f"- VROOM gate: {summary.get('vroomGate')}",
            f"- Gap classifications: `{json.dumps(summary.get('gapClassifications', {}), sort_keys=True)}`",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unified champion-challenger benchmark suites.")
    parser.add_argument("--suite", default="smoke")
    parser.add_argument("--champions", default="vroom")
    parser.add_argument("--challenger", choices=("phase56f",), default="phase56f")
    parser.add_argument("--vroom-url", default="")
    parser.add_argument("--vroom-bin", default="")
    parser.add_argument("--vroom-timeout-seconds", type=int, default=120)
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--mode", choices=("academic_certification", "production_food_dispatch"), default="academic_certification")
    parser.add_argument("--data-source", choices=("fixture", "official", "auto"), default="auto")
    parser.add_argument("--dry-run-conversion", action="store_true")
    parser.add_argument("--skip-vroom-run", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE63 UNIFIED BENCHMARK SUITE] wrote {args.output_dir}")
    return 0 if summary.get("challengerGate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

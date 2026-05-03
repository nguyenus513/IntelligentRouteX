from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def solver_summary(report: dict[str, Any], solver: str) -> dict[str, Any] | None:
    return next((row for row in report.get("solverSummaries", []) if row.get("solver") == solver), None)


def build_report(input_dir: Path, max_runtime_p95_ms: int, max_evidence_gap_rate: float, max_resource_overrun_rate: float = 0.25) -> dict[str, Any]:
    aggregate = read_json(input_dir / "phase15_large_benchmark_report.json")
    ours = solver_summary(aggregate, "our-dispatch-v2")
    blockers: list[str] = []
    if aggregate.get("completedCells") != aggregate.get("totalCells"):
        blockers.append("phase15-incomplete-cells")
    if ours is None:
        blockers.append("phase15-missing-our-dispatch-v2")
    else:
        if int(ours.get("failCount") or 0) > 0:
            blockers.append("phase15-our-failures")
        if int(ours.get("hardViolationCount") or 0) > 0:
            blockers.append("phase15-hard-violations")
        row_count = max(1, int(ours.get("rowCount") or 0))
        evidence_gap_rate = int(ours.get("evidenceGapCount") or 0) / row_count
        if evidence_gap_rate > max_evidence_gap_rate:
            blockers.append("phase15-evidence-gap-rate-too-high")
        runtime_p95 = ours.get("runtimeP95Ms")
        if runtime_p95 is not None and float(runtime_p95) > max_runtime_p95_ms:
            blockers.append("phase15-runtime-p95-too-high")
        resource_summary = ours.get("resourceSummary") or {}
        overrun_rate = resource_summary.get("wallClockOverrunRate")
        if overrun_rate is None:
            overrun_rate = resource_summary.get("overrunRate")
        if overrun_rate is not None and float(overrun_rate) > max_resource_overrun_rate:
            blockers.append("phase15-wall-clock-overrun-rate-too-high")
    if int(aggregate.get("losses") or 0) > 0:
        blockers.append("phase15-comparison-losses")
    wins = int(aggregate.get("wins") or 0)
    losses = int(aggregate.get("losses") or 0)
    comparisons = int(aggregate.get("comparisonCount") or 0)
    if comparisons <= 0:
        blockers.append("phase15-no-baseline-comparisons")
    verdict = "PASS" if not blockers and wins > 0 and losses == 0 else "PASS_WITH_LIMITS" if not blockers else "FAIL"
    return {
        "schemaVersion": "phase15-large-benchmark-gate/v1",
        "inputDir": str(input_dir),
        "tier": aggregate.get("tier"),
        "completedCells": aggregate.get("completedCells"),
        "totalCells": aggregate.get("totalCells"),
        "comparisonCount": comparisons,
        "wins": wins,
        "ties": aggregate.get("ties"),
        "losses": losses,
        "ourSummary": ours,
        "maxRuntimeP95Ms": max_runtime_p95_ms,
        "maxEvidenceGapRate": max_evidence_gap_rate,
        "maxResourceOverrunRate": max_resource_overrun_rate,
        "maxWallClockOverrunRate": max_resource_overrun_rate,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report.get("ourSummary") or {}
    lines = [
        "# Phase 15 Large Benchmark Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- tier: `{report['tier']}`",
        f"- completed cells: `{report['completedCells']}/{report['totalCells']}`",
        f"- wins/ties/losses: `{report['wins']}/{report['ties']}/{report['losses']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "## Our Summary",
        "",
        f"- rows: `{summary.get('rowCount')}`",
        f"- pass/pass-with-limits/fail/evidence-gap: `{summary.get('passCount')}/{summary.get('passWithLimitsCount')}/{summary.get('failCount')}/{summary.get('evidenceGapCount')}`",
        f"- feasible: `{summary.get('feasibleCount')}`",
        f"- vehicle gap sum: `{summary.get('vehicleGapSum')}`",
        f"- hard violations: `{summary.get('hardViolationCount')}`",
        f"- runtime p50/p95/p99: `{summary.get('runtimeP50Ms')}/{summary.get('runtimeP95Ms')}/{summary.get('runtimeP99Ms')}`",
        f"- solver overrun rate: `{(summary.get('resourceSummary') or {}).get('solverOverrunRate')}`",
        f"- wall-clock overrun rate: `{(summary.get('resourceSummary') or {}).get('wallClockOverrunRate')}`",
        f"- budget used p95: `{(summary.get('resourceSummary') or {}).get('budgetUsedP95Ms')}`",
        f"- wall-clock overhead p95: `{(summary.get('resourceSummary') or {}).get('wallClockOverheadP95Ms')}`",
        f"- degrade levels: `{(summary.get('resourceSummary') or {}).get('degradeLevelCounts')}`",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 15 large benchmark gate.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-runtime-p95-ms", type=int, default=15_000)
    parser.add_argument("--max-evidence-gap-rate", type=float, default=0.0)
    parser.add_argument("--max-resource-overrun-rate", type=float, default=None)
    parser.add_argument("--max-wall-clock-overrun-rate", type=float, default=0.25)
    args = parser.parse_args(argv)
    max_overrun_rate = args.max_wall_clock_overrun_rate if args.max_resource_overrun_rate is None else args.max_resource_overrun_rate
    report = build_report(Path(args.input_dir), args.max_runtime_p95_ms, args.max_evidence_gap_rate, max_overrun_rate)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase15_large_benchmark_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase15_large_benchmark_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE15 LARGE GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

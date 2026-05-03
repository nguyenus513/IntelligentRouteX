from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def our_summary(aggregate: dict[str, Any]) -> dict[str, Any] | None:
    return next((row for row in aggregate.get("solverSummaries", []) if row.get("solver") == "our-dispatch-v2"), None)


def build_report(candidate_dir: Path, max_runtime_p95_ms: int, require_full_medium: bool) -> dict[str, Any]:
    result = read_json(candidate_dir / "phase21_medium_benchmark_results.json")
    aggregate = result.get("aggregateReport", {})
    summary = our_summary(aggregate)
    blockers: list[str] = []
    if summary is None:
        blockers.append("phase21-missing-our-summary")
    else:
        if int(summary.get("failCount") or 0) > 0:
            blockers.append("phase21-our-failures")
        if int(summary.get("hardViolationCount") or 0) > 0:
            blockers.append("phase21-hard-violations")
        if float(summary.get("runtimeP95Ms") or 0) > max_runtime_p95_ms:
            blockers.append("phase21-runtime-p95-too-high")
    if int(aggregate.get("losses") or 0) > 0:
        blockers.append("phase21-comparison-losses")
    if aggregate.get("completedCells") != aggregate.get("totalCells"):
        blockers.append("phase21-incomplete-cells")
    if require_full_medium and result.get("instanceLimit"):
        blockers.append("phase21-not-full-medium")
    wins = int(aggregate.get("wins") or 0)
    verdict = "PASS" if not blockers and wins > 0 else "PASS_WITH_LIMITS" if not blockers else "FAIL"
    return {
        "schemaVersion": "phase21-medium-benchmark-gate/v1",
        "candidateDir": str(candidate_dir),
        "completedCells": aggregate.get("completedCells"),
        "totalCells": aggregate.get("totalCells"),
        "wins": wins,
        "ties": aggregate.get("ties"),
        "losses": aggregate.get("losses"),
        "ourSummary": summary,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report.get("ourSummary") or {}
    return "\n".join([
        "# Phase 21 Medium Benchmark Gate",
        "",
        f"- verdict: `{report['verdict']}`",
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
        "",
    ])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 21 medium benchmark gate.")
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-runtime-p95-ms", type=int, default=15_000)
    parser.add_argument("--require-full-medium", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(Path(args.candidate_dir), args.max_runtime_p95_ms, args.require_full_medium)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase21_medium_benchmark_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase21_medium_benchmark_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE21 MEDIUM BENCHMARK GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

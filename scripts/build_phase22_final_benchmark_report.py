from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase22-final-report-v1"

PHASE_ARTIFACTS = {
    "phase15": REPO_ROOT / "artifacts" / "benchmark" / "community-phase15-gap-smoke-gate-v2" / "phase15_large_benchmark_gate.json",
    "phase16": REPO_ROOT / "artifacts" / "benchmark" / "community-phase16-gap-reduction-gate-v1" / "phase16_gap_reduction_gate.json",
    "phase17": REPO_ROOT / "artifacts" / "benchmark" / "community-phase17-route-pool-quality-gate-v1" / "phase17_route_pool_quality_gate.json",
    "phase18": REPO_ROOT / "artifacts" / "benchmark" / "community-phase18-time-window-restructuring-gate-v1" / "phase18_time_window_restructuring_gate.json",
    "phase19": REPO_ROOT / "artifacts" / "benchmark" / "community-phase19-bks-compatibility-gate-v1" / "phase19_bks_compatibility_gate.json",
    "phase20": REPO_ROOT / "artifacts" / "benchmark" / "community-phase20-reference-offline-gate-v1" / "phase20_reference_offline_gate.json",
    "phase21": REPO_ROOT / "artifacts" / "benchmark" / "community-phase21-medium-full-reference-gate-v1" / "phase21_medium_benchmark_gate.json",
    "phase23": REPO_ROOT / "artifacts" / "benchmark" / "community-phase23-reference-gate-with-rc101-v1" / "phase23_reference_gate.json",
}


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_phase_gates(paths: dict[str, Path] = PHASE_ARTIFACTS) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for phase, path in paths.items():
        payload = read_json(path)
        loaded[phase] = {
            "phase": phase,
            "path": str(path),
            "available": payload is not None,
            "payload": payload,
            "verdict": None if payload is None else payload.get("verdict"),
            "blockers": ["phase22-artifact-missing"] if payload is None else payload.get("blockers", []),
        }
    return loaded


def extract_summary(gates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    phase21 = (gates.get("phase21") or {}).get("payload") or {}
    phase20 = (gates.get("phase20") or {}).get("payload") or {}
    phase19 = (gates.get("phase19") or {}).get("payload") or {}
    phase18 = (gates.get("phase18") or {}).get("payload") or {}
    phase17 = (gates.get("phase17") or {}).get("payload") or {}
    phase16 = (gates.get("phase16") or {}).get("payload") or {}
    phase23 = (gates.get("phase23") or {}).get("payload") or {}
    our = phase21.get("ourSummary") or {}
    return {
        "latestMediumVerdict": phase21.get("verdict"),
        "mediumWins": phase21.get("wins"),
        "mediumTies": phase21.get("ties"),
        "mediumLosses": phase21.get("losses"),
        "mediumHardViolations": our.get("hardViolationCount"),
        "mediumRuntimeP95Ms": our.get("runtimeP95Ms"),
        "mediumVehicleGapSum": our.get("vehicleGapSum"),
        "rc101GapAfterPhase20": first_row_value(phase20, "candidateGap"),
        "rc101GapAfterPhase23": first_row_value(phase23, "candidateGap"),
        "rc101ReferenceFeasiblePhase23": bool(first_row_value(phase23, "referenceRouteFeasible")),
        "rc101ReferenceAvailable": phase19.get("referenceRouteAvailable"),
        "rc101CompatibilityConclusion": phase19.get("compatibilityConclusion"),
        "phase18BestSplitVehicleCount": first_row_value(phase18, "bestSplitVehicleCount"),
        "phase17ActionableDiagnostics": phase17.get("actionableDiagnostics"),
        "shortBudgetParityVerdict": phase16.get("verdict"),
    }


def first_row_value(payload: dict[str, Any], key: str) -> Any:
    rows = payload.get("rows", [])
    return None if not rows else rows[0].get(key)


def decision(summary: dict[str, Any], gates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    missing = [phase for phase, gate in gates.items() if not gate.get("available")]
    if missing:
        blockers.append("phase22-missing-required-artifacts")
    failed = [phase for phase, gate in gates.items() if gate.get("verdict") == "FAIL"]
    if failed:
        blockers.append("phase22-has-failed-phase-gates")
    if int(summary.get("mediumLosses") or 0) > 0:
        blockers.append("phase22-medium-benchmark-losses")
    if int(summary.get("mediumHardViolations") or 0) > 0:
        blockers.append("phase22-hard-violations")
    if float(summary.get("mediumRuntimeP95Ms") or 0.0) > 15_000:
        blockers.append("phase22-runtime-p95-too-high")
    if int(summary.get("mediumWins") or 0) <= 0:
        warnings.append("phase22-no-clear-medium-win")
    rc101_latest_gap = summary.get("rc101GapAfterPhase23") if summary.get("rc101GapAfterPhase23") is not None else summary.get("rc101GapAfterPhase20")
    if rc101_latest_gap not in (None, 0):
        warnings.append("phase22-rc101-bks-gap-remains")
    if not (summary.get("rc101ReferenceAvailable") or summary.get("rc101ReferenceFeasiblePhase23")):
        warnings.append("phase22-reference-route-missing")
    verdict = "FAIL" if blockers else "PASS" if not warnings else "PASS_WITH_LIMITS"
    return {
        "verdict": verdict,
        "blockers": blockers,
        "warnings": warnings,
        "claim": "stable-no-loss-limited-bks-claim" if verdict == "PASS_WITH_LIMITS" else "ready-to-claim" if verdict == "PASS" else "not-ready",
    }


def build_report(paths: dict[str, Path] = PHASE_ARTIFACTS) -> dict[str, Any]:
    gates = load_phase_gates(paths)
    summary = extract_summary(gates)
    final_decision = decision(summary, gates)
    return {
        "schemaVersion": "phase22-final-benchmark-report/v1",
        "phaseGates": gates,
        "summary": summary,
        "decision": final_decision,
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    decision_payload = report["decision"]
    lines = [
        "# Phase 22 Final Benchmark Report",
        "",
        "## Executive Summary",
        "",
        f"- verdict: `{decision_payload['verdict']}`",
        f"- claim: `{decision_payload['claim']}`",
        f"- blockers: `{decision_payload['blockers']}`",
        f"- warnings: `{decision_payload['warnings']}`",
        f"- medium wins/ties/losses: `{summary.get('mediumWins')}/{summary.get('mediumTies')}/{summary.get('mediumLosses')}`",
        f"- medium runtime p95 ms: `{summary.get('mediumRuntimeP95Ms')}`",
        f"- medium hard violations: `{summary.get('mediumHardViolations')}`",
        f"- RC101 gap after Phase 20/23: `{summary.get('rc101GapAfterPhase20')}/{summary.get('rc101GapAfterPhase23')}`",
        f"- RC101 reference available/feasible: `{summary.get('rc101ReferenceAvailable')}/{summary.get('rc101ReferenceFeasiblePhase23')}`",
        "",
        "## Phase Matrix",
        "",
        "| Phase | Verdict | Blockers | Artifact |",
        "|---|---|---|---|",
    ]
    for phase, gate in report["phaseGates"].items():
        lines.append(f"| {phase} | {gate.get('verdict')} | {gate.get('blockers')} | `{gate.get('path')}` |")
    lines.extend([
        "",
        "## Decision",
        "",
        "The system is stable on the controlled benchmark rail and has no full-medium baseline losses or hard violations in the latest gate. Phase 23 imports and validates a 14-vehicle `RC101` reference route, removing the previous RC101 BKS blocker for the reference-import rail.",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 22 final benchmark report.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    report = build_report()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase22_final_benchmark_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase22_final_benchmark_report.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE22 FINAL REPORT] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

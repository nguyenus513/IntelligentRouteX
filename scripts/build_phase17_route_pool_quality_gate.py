from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(candidate_dir: Path, time_limit_ms: int) -> dict[str, Any]:
    payload = read_json(candidate_dir / "phase17_route_pool_quality_results.json")
    rows = []
    blockers: list[str] = []
    total_delta = 0
    actionable = False
    for row in payload.get("results", []):
        row_blockers = []
        seed_gap = row.get("seedVehicleGap")
        candidate_gap = row.get("vehicleGap")
        if row.get("status") == "FAIL" or not row.get("feasible"):
            row_blockers.append("phase17-target-failed")
        if int(row.get("hardViolationCount") or 0) > 0:
            row_blockers.append("phase17-hard-violations")
        if int(row.get("runtimeMs") or 0) > time_limit_ms:
            row_blockers.append("phase17-runtime-timeout")
        if int(row.get("routePoolSizeAfter") or 0) <= int(row.get("routePoolSizeBefore") or 0):
            row_blockers.append("phase17-route-pool-not-expanded")
        if not bool(row.get("setPartitioningProducedSolution")):
            row_blockers.append("phase17-set-partitioning-not-produced")
        if seed_gap is not None and candidate_gap is not None:
            delta = int(seed_gap) - int(candidate_gap)
            total_delta += delta
            if delta < 0:
                row_blockers.append("phase17-gap-regressed")
        diagnostics = row.get("diagnosticsAfter", {}) if isinstance(row.get("diagnosticsAfter"), dict) else {}
        coverage = diagnostics.get("coverage", {}) if isinstance(diagnostics.get("coverage"), dict) else {}
        merge = diagnostics.get("mergeDiagnostics", {}) if isinstance(diagnostics.get("mergeDiagnostics"), dict) else {}
        if coverage.get("lowCoverageCustomerCount") is not None or merge.get("mergeRejectReasons"):
            actionable = True
        blockers.extend(row_blockers)
        rows.append({
            "suite": row.get("suite"),
            "instance": row.get("instance"),
            "status": row.get("status"),
            "seedGap": seed_gap,
            "candidateGap": candidate_gap,
            "gapDelta": None if seed_gap is None or candidate_gap is None else int(seed_gap) - int(candidate_gap),
            "routePoolSizeBefore": row.get("routePoolSizeBefore"),
            "routePoolSizeAfter": row.get("routePoolSizeAfter"),
            "setPartitioningProducedSolution": row.get("setPartitioningProducedSolution"),
            "runtimeMs": row.get("runtimeMs"),
            "actionableNextStep": diagnostics.get("actionableNextStep"),
            "lowCoverageCustomerCount": coverage.get("lowCoverageCustomerCount"),
            "mergeRejectReasons": merge.get("mergeRejectReasons"),
            "blockers": row_blockers,
        })
    verdict = "PASS" if not blockers and total_delta > 0 else "PASS_WITH_LIMITS" if not blockers and actionable else "FAIL"
    return {
        "schemaVersion": "phase17-route-pool-quality-gate/v1",
        "candidateDir": str(candidate_dir),
        "rowCount": len(rows),
        "totalGapDelta": total_delta,
        "actionableDiagnostics": actionable,
        "rows": rows,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 17 Route Pool Quality Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- total gap delta: `{report['totalGapDelta']}`",
        f"- actionable diagnostics: `{report['actionableDiagnostics']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Status | Gap Seed/After | Pool Before/After | SP | Runtime | Low Coverage | Action | Blockers |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('seedGap')}/{row.get('candidateGap')} | "
            f"{row.get('routePoolSizeBefore')}/{row.get('routePoolSizeAfter')} | {row.get('setPartitioningProducedSolution')} | "
            f"{row.get('runtimeMs')} | {row.get('lowCoverageCustomerCount')} | {row.get('actionableNextStep')} | {row.get('blockers')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 17 route-pool quality gate.")
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--time-limit-ms", type=int, default=15_000)
    args = parser.parse_args(argv)
    report = build_report(Path(args.candidate_dir), args.time_limit_ms)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase17_route_pool_quality_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase17_route_pool_quality_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE17 ROUTE POOL QUALITY GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

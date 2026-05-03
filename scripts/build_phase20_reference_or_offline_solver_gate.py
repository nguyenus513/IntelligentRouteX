from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(candidate_dir: Path, time_limit_ms: int) -> dict[str, Any]:
    payload = read_json(candidate_dir / "phase20_reference_offline_results.json")
    rows = []
    blockers: list[str] = []
    total_delta = 0
    evidence = False
    for row in payload.get("results", []):
        row_blockers = []
        seed_gap = row.get("seedVehicleGap")
        candidate_gap = row.get("vehicleGap")
        if row.get("status") == "FAIL" or not row.get("feasible"):
            row_blockers.append("phase20-final-infeasible")
        if int(row.get("hardViolationCount") or 0) > 0:
            row_blockers.append("phase20-hard-violations")
        if int(row.get("runtimeMs") or 0) > time_limit_ms:
            row_blockers.append("phase20-runtime-timeout")
        if int(row.get("offlineRunCount") or 0) <= 0 and not bool(row.get("referenceRouteAvailable")):
            row_blockers.append("phase20-no-reference-or-offline-evidence")
        if int(row.get("routePoolSizeAfter") or 0) <= int(row.get("routePoolSizeBefore") or 0):
            row_blockers.append("phase20-route-pool-not-expanded")
        if not bool(row.get("setPartitioningProducedSolution")):
            row_blockers.append("phase20-set-partitioning-not-produced")
        if seed_gap is not None and candidate_gap is not None:
            delta = int(seed_gap) - int(candidate_gap)
            total_delta += delta
            if delta < 0:
                row_blockers.append("phase20-gap-regressed")
        if bool(row.get("referenceRouteAvailable")) or int(row.get("offlineRunCount") or 0) > 0:
            evidence = True
        blockers.extend(row_blockers)
        rows.append({
            "suite": row.get("suite"),
            "instance": row.get("instance"),
            "status": row.get("status"),
            "seedGap": seed_gap,
            "candidateGap": candidate_gap,
            "gapDelta": None if seed_gap is None or candidate_gap is None else int(seed_gap) - int(candidate_gap),
            "referenceRouteAvailable": row.get("referenceRouteAvailable"),
            "referenceRouteFeasible": row.get("referenceRouteFeasible"),
            "offlineRunCount": row.get("offlineRunCount"),
            "offlineFeasibleRunCount": row.get("offlineFeasibleRunCount"),
            "bestOfflineVehicleCount": row.get("bestOfflineVehicleCount"),
            "routePoolSizeBefore": row.get("routePoolSizeBefore"),
            "routePoolSizeAfter": row.get("routePoolSizeAfter"),
            "setPartitioningProducedSolution": row.get("setPartitioningProducedSolution"),
            "bestLabel": row.get("bestLabel"),
            "runtimeMs": row.get("runtimeMs"),
            "blockers": row_blockers,
        })
    verdict = "PASS" if not blockers and total_delta > 0 else "PASS_WITH_LIMITS" if not blockers and evidence else "FAIL"
    return {
        "schemaVersion": "phase20-reference-offline-gate/v1",
        "candidateDir": str(candidate_dir),
        "rowCount": len(rows),
        "totalGapDelta": total_delta,
        "referenceOrOfflineEvidence": evidence,
        "rows": rows,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 20 Reference / Offline Solver Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- total gap delta: `{report['totalGapDelta']}`",
        f"- reference/offline evidence: `{report['referenceOrOfflineEvidence']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Status | Gap Seed/After | Ref | Offline Runs | Best Offline | Pool Before/After | SP | Best Label | Runtime | Blockers |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('seedGap')}/{row.get('candidateGap')} | "
            f"{row.get('referenceRouteAvailable')}/{row.get('referenceRouteFeasible')} | {row.get('offlineRunCount')}/{row.get('offlineFeasibleRunCount')} | "
            f"{row.get('bestOfflineVehicleCount')} | {row.get('routePoolSizeBefore')}/{row.get('routePoolSizeAfter')} | "
            f"{row.get('setPartitioningProducedSolution')} | {row.get('bestLabel')} | {row.get('runtimeMs')} | {row.get('blockers')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 20 reference/offline solver gate.")
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--time-limit-ms", type=int, default=60_000)
    args = parser.parse_args(argv)
    report = build_report(Path(args.candidate_dir), args.time_limit_ms)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase20_reference_offline_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase20_reference_offline_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE20 REFERENCE OFFLINE GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

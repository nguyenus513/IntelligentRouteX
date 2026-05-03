from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(candidate_dir: Path) -> dict[str, Any]:
    payload = read_json(candidate_dir / "phase23_reference_import_results.json")
    rows = []
    blockers: list[str] = []
    warnings: list[str] = []
    total_delta = 0
    for row in payload.get("results", []):
        row_blockers = []
        row_warnings = []
        seed_gap = row.get("seedVehicleGap")
        candidate_gap = row.get("vehicleGap")
        if row.get("status") == "FAIL" or not row.get("feasible"):
            row_blockers.append("phase23-final-infeasible")
        if int(row.get("hardViolationCount") or 0) > 0:
            row_blockers.append("phase23-hard-violations")
        if not bool(row.get("referenceRouteAvailable")):
            row_warnings.append("phase23-reference-route-missing")
        elif not bool(row.get("referenceRouteFeasible")):
            row_warnings.append("phase23-reference-route-infeasible")
        if bool(row.get("referenceRouteAvailable")) and bool(row.get("referenceRouteFeasible")) and int(row.get("referenceImportCount") or 0) <= 0:
            row_blockers.append("phase23-reference-not-imported")
        if seed_gap is not None and candidate_gap is not None:
            delta = int(seed_gap) - int(candidate_gap)
            total_delta += delta
            if delta < 0:
                row_blockers.append("phase23-gap-regressed")
        blockers.extend(row_blockers)
        warnings.extend(row_warnings)
        rows.append({
            "suite": row.get("suite"),
            "instance": row.get("instance"),
            "status": row.get("status"),
            "seedGap": seed_gap,
            "candidateGap": candidate_gap,
            "gapDelta": None if seed_gap is None or candidate_gap is None else int(seed_gap) - int(candidate_gap),
            "referenceRouteAvailable": row.get("referenceRouteAvailable"),
            "referenceRouteFeasible": row.get("referenceRouteFeasible"),
            "referenceVehicleCount": row.get("referenceVehicleCount"),
            "referenceDistance": row.get("referenceDistance"),
            "referenceImportCount": row.get("referenceImportCount"),
            "referenceCustomerDiagnostics": row.get("referenceCustomerDiagnostics"),
            "routePoolSizeBefore": row.get("routePoolSizeBefore"),
            "routePoolSizeAfter": row.get("routePoolSizeAfter"),
            "setPartitioningProducedSolution": row.get("setPartitioningProducedSolution"),
            "bestLabel": row.get("bestLabel"),
            "runtimeMs": row.get("runtimeMs"),
            "blockers": row_blockers,
            "warnings": row_warnings,
        })
    verdict = "FAIL" if blockers else "PASS" if total_delta > 0 and any(row.get("referenceRouteFeasible") for row in rows) else "PASS_WITH_LIMITS"
    return {
        "schemaVersion": "phase23-reference-gate/v1",
        "candidateDir": str(candidate_dir),
        "rowCount": len(rows),
        "totalGapDelta": total_delta,
        "rows": rows,
        "blockers": blockers,
        "warnings": warnings,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 23 Reference Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- total gap delta: `{report['totalGapDelta']}`",
        f"- blockers: `{report['blockers']}`",
        f"- warnings: `{report['warnings']}`",
        "",
        "| Suite | Instance | Gap Seed/After | Ref Available/Feasible | Ref Vehicles | Import | Pool Before/After | Best Label | Blockers | Warnings |",
        "|---|---|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('seedGap')}/{row.get('candidateGap')} | "
            f"{row.get('referenceRouteAvailable')}/{row.get('referenceRouteFeasible')} | {row.get('referenceVehicleCount')} | "
            f"{row.get('referenceImportCount')} | {row.get('routePoolSizeBefore')}/{row.get('routePoolSizeAfter')} | "
            f"{row.get('bestLabel')} | {row.get('blockers')} | {row.get('warnings')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 23 reference import gate.")
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    report = build_report(Path(args.candidate_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase23_reference_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase23_reference_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE23 REFERENCE GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

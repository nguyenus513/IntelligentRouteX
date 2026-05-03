from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

TARGETS = {("solomon", "RC101"), ("li-lim", "LR101"), ("li-lim", "LRC101")}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    for filename in ("phase14_pyvrp_calibration_results.json", "phase12_route_pool_results.json"):
        path = root / filename
        if path.exists():
            payload = read_json(path)
            return {(str(row.get("suite", "")), str(row.get("instance", ""))): row for row in payload.get("results", [])}
    return {}


def build_report(baseline_dir: Path, candidate_dir: Path, time_limit_ms: int) -> dict[str, Any]:
    baseline = load_rows(baseline_dir)
    candidate = load_rows(candidate_dir)
    rows = []
    blockers: list[str] = []
    for key in sorted(TARGETS):
        row = candidate.get(key)
        base = baseline.get(key, {})
        if row is None:
            rows.append({"suite": key[0], "instance": key[1], "blockers": ["phase14-missing-target"]})
            blockers.append("phase14-missing-target")
            continue
        row_blockers = []
        baseline_gap = base.get("vehicleGap")
        candidate_gap = row.get("vehicleGap")
        if row.get("status") == "FAIL":
            row_blockers.append("phase14-target-failed")
        if key[0] == "solomon":
            if int(row.get("hgsVariantCount") or 0) <= 0:
                row_blockers.append("phase14-no-hgs-variant-run")
            if int(row.get("hgsPassCount") or 0) <= 0:
                row_blockers.append("phase14-no-hgs-pass")
            if int(row.get("routePoolSizeAfterHgs") or 0) <= int(row.get("routePoolSizeBeforeHgs") or 0):
                row_blockers.append("phase14-hgs-routes-not-added")
            if not bool(row.get("setPartitioningProducedSolution")):
                row_blockers.append("phase14-set-partitioning-not-produced")
        if candidate_gap is not None and baseline_gap is not None and int(candidate_gap) > int(baseline_gap):
            row_blockers.append("phase14-gap-regressed")
        if int(row.get("runtimeMs") or 0) > time_limit_ms:
            row_blockers.append("phase14-runtime-timeout")
        blockers.extend(row_blockers)
        rows.append({
            "suite": key[0],
            "instance": key[1],
            "status": row.get("status"),
            "baselineGap": baseline_gap,
            "candidateGap": candidate_gap,
            "gapDelta": None if baseline_gap is None or candidate_gap is None else int(baseline_gap) - int(candidate_gap),
            "hgsVariantCount": row.get("hgsVariantCount"),
            "hgsPassCount": row.get("hgsPassCount"),
            "bestHgsVariant": row.get("bestHgsVariant"),
            "bestHgsVehicleCount": row.get("bestHgsVehicleCount"),
            "routePoolSizeBeforeHgs": row.get("routePoolSizeBeforeHgs"),
            "routePoolSizeAfterHgs": row.get("routePoolSizeAfterHgs"),
            "setPartitioningProducedSolution": row.get("setPartitioningProducedSolution"),
            "bestLabel": row.get("bestLabel"),
            "runtimeMs": row.get("runtimeMs"),
            "reasons": row.get("reasons", []),
            "blockers": row_blockers,
        })
    measured = [row for row in rows if row.get("baselineGap") is not None and row.get("candidateGap") is not None]
    total_delta = sum(int(row["baselineGap"]) - int(row["candidateGap"]) for row in measured)
    calibration_evidence = any(int(row.get("hgsVariantCount") or 0) > 1 and int(row.get("hgsPassCount") or 0) > 0 for row in rows)
    verdict = "PASS" if not blockers and total_delta > 0 else "PASS_WITH_LIMITS" if not blockers and calibration_evidence else "FAIL"
    return {
        "schemaVersion": "phase14-pyvrp-calibration-gate/v1",
        "baselineDir": str(baseline_dir),
        "candidateDir": str(candidate_dir),
        "rowCount": len(rows),
        "totalGapDelta": total_delta,
        "calibrationEvidence": calibration_evidence,
        "rows": rows,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 14 PyVRP Calibration Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- total gap delta: `{report['totalGapDelta']}`",
        f"- calibration evidence: `{report['calibrationEvidence']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Status | Gap B/C | HGS Variants | HGS Pass | Best HGS | HGS Vehicles | Pool Before/After | SP | Best Label | Runtime | Blockers |",
        "|---|---|---|---:|---:|---:|---|---:|---:|---:|---|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('baselineGap')}/{row.get('candidateGap')} | "
            f"{row.get('hgsVariantCount')} | {row.get('hgsPassCount')} | {row.get('bestHgsVariant')} | {row.get('bestHgsVehicleCount')} | "
            f"{row.get('routePoolSizeBeforeHgs')}/{row.get('routePoolSizeAfterHgs')} | {row.get('setPartitioningProducedSolution')} | "
            f"{row.get('bestLabel')} | {row.get('runtimeMs')} | {row.get('blockers')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 14 PyVRP calibration gate.")
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--time-limit-ms", type=int, default=15_000)
    args = parser.parse_args(argv)
    report = build_report(Path(args.baseline_dir), Path(args.candidate_dir), args.time_limit_ms)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase14_pyvrp_calibration_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase14_pyvrp_calibration_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE14 PYVRP CALIBRATION GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

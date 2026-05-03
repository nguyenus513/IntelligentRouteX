from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

TARGETS = {("solomon", "RC101"), ("li-lim", "LR101"), ("li-lim", "LRC101")}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_baseline_gaps(root: Path) -> dict[tuple[str, str], int]:
    gaps: dict[tuple[str, str], int] = {}
    payload_path = root / "phase12_route_pool_results.json"
    if payload_path.exists():
        for row in read_json(payload_path).get("results", []):
            key = (str(row.get("suite", "")), str(row.get("instance", "")))
            if row.get("vehicleGap") is not None:
                gaps[key] = int(row["vehicleGap"])
    for path in root.rglob("external_benchmark_results.json"):
        for row in read_json(path).get("results", []):
            if row.get("solver") != "our-dispatch-v2":
                continue
            key = (str(row.get("suite", "")), str(row.get("instance", "")))
            if row.get("vehicleCount") is not None and row.get("bestKnownVehicleCount") is not None:
                gaps[key] = max(0, int(row["vehicleCount"]) - int(row["bestKnownVehicleCount"]))
    return gaps


def build_report(baseline_dir: Path, candidate_dir: Path, time_limit_ms: int) -> dict[str, Any]:
    baseline = load_baseline_gaps(baseline_dir)
    payload = read_json(candidate_dir / "phase12_route_pool_results.json")
    candidates = {(str(row.get("suite", "")), str(row.get("instance", ""))): row for row in payload.get("results", [])}
    rows = []
    blockers: list[str] = []
    for key in sorted(TARGETS):
        row = candidates.get(key)
        row_blockers: list[str] = []
        if row is None:
            row_blockers.append("phase13-missing-target")
            rows.append({"suite": key[0], "instance": key[1], "blockers": row_blockers})
            blockers.extend(row_blockers)
            continue
        baseline_gap = baseline.get(key)
        candidate_gap = row.get("vehicleGap")
        hgs_available = bool(row.get("hgsAvailable", False))
        if row.get("status") == "FAIL":
            row_blockers.append("phase13-target-failed")
        if key[0] == "solomon" and hgs_available:
            if row.get("hgsStatus") != "PASS":
                row_blockers.append("phase13-hgs-not-pass")
            if int(row.get("hgsRoutesImported") or 0) <= 0:
                row_blockers.append("phase13-hgs-routes-not-imported")
            if not bool(row.get("setPartitioningProducedSolution")):
                row_blockers.append("phase13-set-partitioning-not-produced")
        if key[0] == "solomon" and int(row.get("routePoolSize") or 0) <= 0:
            row_blockers.append("phase13-route-pool-empty")
        if candidate_gap is not None and baseline_gap is not None and int(candidate_gap) > int(baseline_gap):
            row_blockers.append("phase13-gap-regressed")
        if int(row.get("runtimeMs") or 0) > time_limit_ms:
            row_blockers.append("phase13-runtime-timeout")
        blockers.extend(row_blockers)
        rows.append({
            "suite": key[0],
            "instance": key[1],
            "status": row.get("status"),
            "baselineGap": baseline_gap,
            "candidateGap": candidate_gap,
            "gapDelta": None if baseline_gap is None or candidate_gap is None else int(baseline_gap) - int(candidate_gap),
            "routePoolSize": row.get("routePoolSize"),
            "hgsAvailable": hgs_available,
            "hgsStatus": row.get("hgsStatus"),
            "hgsVehicleCount": row.get("hgsVehicleCount"),
            "hgsRoutesImported": row.get("hgsRoutesImported"),
            "hgsEvidenceGapReason": row.get("hgsEvidenceGapReason"),
            "setPartitioningProducedSolution": row.get("setPartitioningProducedSolution"),
            "runtimeMs": row.get("runtimeMs"),
            "reasons": row.get("reasons", []),
            "blockers": row_blockers,
        })
    measured = [row for row in rows if row.get("baselineGap") is not None and row.get("candidateGap") is not None]
    total_delta = sum(int(row["baselineGap"]) - int(row["candidateGap"]) for row in measured)
    hgs_evidence = any(row.get("hgsAvailable") and int(row.get("hgsRoutesImported") or 0) > 0 for row in rows)
    skipped_hgs = any(row.get("hgsEvidenceGapReason") for row in rows)
    verdict = "PASS" if not blockers and total_delta > 0 else "PASS_WITH_LIMITS" if not blockers and (hgs_evidence or skipped_hgs) else "FAIL"
    return {
        "schemaVersion": "phase13-hgs-route-pool-gate/v1",
        "baselineDir": str(baseline_dir),
        "candidateDir": str(candidate_dir),
        "rowCount": len(rows),
        "totalGapDelta": total_delta,
        "hgsEvidence": hgs_evidence,
        "skippedHgs": skipped_hgs,
        "rows": rows,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 13 HGS Route Pool Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- total gap delta: `{report['totalGapDelta']}`",
        f"- HGS evidence: `{report['hgsEvidence']}`",
        f"- skipped HGS: `{report['skippedHgs']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Status | Gap B/C | Pool | HGS | HGS Vehicles | Imported | SP | Runtime | Reasons | Blockers |",
        "|---|---|---|---:|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('baselineGap')}/{row.get('candidateGap')} | "
            f"{row.get('routePoolSize')} | {row.get('hgsStatus')} | {row.get('hgsVehicleCount')} | {row.get('hgsRoutesImported')} | "
            f"{row.get('setPartitioningProducedSolution')} | {row.get('runtimeMs')} | {row.get('reasons')} | {row.get('blockers')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 13 HGS route-pool gate.")
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--time-limit-ms", type=int, default=15_000)
    args = parser.parse_args(argv)
    report = build_report(Path(args.baseline_dir), Path(args.candidate_dir), args.time_limit_ms)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase13_hgs_route_pool_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase13_hgs_route_pool_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE13 HGS ROUTE POOL GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

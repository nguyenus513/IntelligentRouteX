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
    for path in root.rglob("external_benchmark_results.json"):
        payload = read_json(path)
        for row in payload.get("results", []):
            if row.get("solver") != "our-dispatch-v2":
                continue
            key = (str(row.get("suite", "")), str(row.get("instance", "")))
            if key not in TARGETS:
                continue
            if row.get("vehicleCount") is None or row.get("bestKnownVehicleCount") is None:
                continue
            gaps[key] = max(0, int(row["vehicleCount"]) - int(row["bestKnownVehicleCount"]))
    return gaps


def load_candidate_rows(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload = read_json(path / "phase12_route_pool_results.json")
    return {(str(row.get("suite", "")), str(row.get("instance", ""))): row for row in payload.get("results", [])}


def build_report(baseline_dir: Path, candidate_dir: Path) -> dict[str, Any]:
    baseline = load_baseline_gaps(baseline_dir)
    candidate = load_candidate_rows(candidate_dir)
    rows = []
    blockers: list[str] = []
    for key in sorted(TARGETS):
        row = candidate.get(key)
        if row is None:
            rows.append({"suite": key[0], "instance": key[1], "blockers": ["phase12-missing-target"]})
            blockers.append("phase12-missing-target")
            continue
        row_blockers = []
        baseline_gap = baseline.get(key)
        candidate_gap = row.get("vehicleGap")
        if row.get("status") == "FAIL":
            row_blockers.append("phase12-target-failed")
        if key[0] == "solomon" and int(row.get("routePoolSize") or 0) <= 0:
            row_blockers.append("phase12-route-pool-empty")
        if key[0] == "solomon" and not bool(row.get("setPartitioningProducedSolution")):
            row_blockers.append("phase12-set-partitioning-not-produced")
        if candidate_gap is not None and baseline_gap is not None and int(candidate_gap) > int(baseline_gap):
            row_blockers.append("phase12-gap-regressed")
        blockers.extend(row_blockers)
        rows.append({
            "suite": key[0],
            "instance": key[1],
            "status": row.get("status"),
            "baselineGap": baseline_gap,
            "candidateGap": candidate_gap,
            "gapDelta": None if baseline_gap is None or candidate_gap is None else int(baseline_gap) - int(candidate_gap),
            "routePoolSize": row.get("routePoolSize"),
            "setPartitioningProducedSolution": row.get("setPartitioningProducedSolution"),
            "bestLabel": row.get("bestLabel"),
            "runtimeMs": row.get("runtimeMs"),
            "reasons": row.get("reasons", []),
            "blockers": row_blockers,
        })
    measured = [row for row in rows if row.get("baselineGap") is not None and row.get("candidateGap") is not None]
    total_delta = sum(int(row["baselineGap"]) - int(row["candidateGap"]) for row in measured)
    has_seed_evidence = any(int(row.get("routePoolSize") or 0) > 0 and row.get("setPartitioningProducedSolution") for row in rows)
    verdict = "PASS" if not blockers and total_delta > 0 else "PASS_WITH_LIMITS" if not blockers and has_seed_evidence else "FAIL"
    return {
        "schemaVersion": "phase12-route-pool-gate/v1",
        "baselineDir": str(baseline_dir),
        "candidateDir": str(candidate_dir),
        "rowCount": len(rows),
        "totalGapDelta": total_delta,
        "hasSeedEvidence": has_seed_evidence,
        "rows": rows,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 12 Route Pool Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- total gap delta: `{report['totalGapDelta']}`",
        f"- seed evidence: `{report['hasSeedEvidence']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Status | Gap B/C | Pool | SP | Best Label | Runtime | Reasons | Blockers |",
        "|---|---|---|---:|---:|---:|---|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('baselineGap')}/{row.get('candidateGap')} | "
            f"{row.get('routePoolSize')} | {row.get('setPartitioningProducedSolution')} | {row.get('bestLabel')} | {row.get('runtimeMs')} | "
            f"{row.get('reasons')} | {row.get('blockers')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 12 route-pool seeding gate.")
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    report = build_report(Path(args.baseline_dir), Path(args.candidate_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase12_route_pool_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase12_route_pool_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE12 ROUTE POOL GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

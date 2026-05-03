from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(candidate_dir: Path, time_limit_ms: int) -> dict[str, Any]:
    payload = read_json(candidate_dir / "phase18_time_window_restructuring_results.json")
    rows = []
    blockers: list[str] = []
    total_delta = 0
    split_evidence = False
    for row in payload.get("results", []):
        row_blockers = []
        seed_gap = row.get("seedVehicleGap")
        candidate_gap = row.get("vehicleGap")
        if row.get("status") == "FAIL" or not row.get("feasible"):
            row_blockers.append("phase18-target-failed")
        if int(row.get("hardViolationCount") or 0) > 0:
            row_blockers.append("phase18-hard-violations")
        if int(row.get("runtimeMs") or 0) > time_limit_ms:
            row_blockers.append("phase18-runtime-timeout")
        if int(row.get("routePoolSizeAfter") or 0) <= int(row.get("routePoolSizeBefore") or 0):
            row_blockers.append("phase18-route-pool-not-expanded")
        if not bool(row.get("setPartitioningProducedSolution")):
            row_blockers.append("phase18-set-partitioning-not-produced")
        if int(row.get("splitCandidateCount") or 0) <= 0:
            row_blockers.append("phase18-no-split-candidates")
        if int(row.get("splitFeasibleCount") or 0) <= 0:
            row_blockers.append("phase18-no-feasible-splits")
        if seed_gap is not None and candidate_gap is not None:
            delta = int(seed_gap) - int(candidate_gap)
            total_delta += delta
            if delta < 0:
                row_blockers.append("phase18-gap-regressed")
        if int(row.get("splitCandidateCount") or 0) > 0 and row.get("bestSplitVehicleCount") is not None:
            split_evidence = True
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
            "splitCandidateCount": row.get("splitCandidateCount"),
            "splitFeasibleCount": row.get("splitFeasibleCount"),
            "bestSplitStrategy": row.get("bestSplitStrategy"),
            "bestSplitVehicleCount": row.get("bestSplitVehicleCount"),
            "setPartitioningProducedSolution": row.get("setPartitioningProducedSolution"),
            "runtimeMs": row.get("runtimeMs"),
            "blockers": row_blockers,
        })
    verdict = "PASS" if not blockers and total_delta > 0 else "PASS_WITH_LIMITS" if not blockers and split_evidence else "FAIL"
    return {
        "schemaVersion": "phase18-time-window-restructuring-gate/v1",
        "candidateDir": str(candidate_dir),
        "rowCount": len(rows),
        "totalGapDelta": total_delta,
        "splitEvidence": split_evidence,
        "rows": rows,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 18 Time-Window Restructuring Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- total gap delta: `{report['totalGapDelta']}`",
        f"- split evidence: `{report['splitEvidence']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Status | Gap Seed/After | Pool Before/After | Splits | Best Split | SP | Runtime | Blockers |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('status')} | {row.get('seedGap')}/{row.get('candidateGap')} | "
            f"{row.get('routePoolSizeBefore')}/{row.get('routePoolSizeAfter')} | {row.get('splitCandidateCount')} | "
            f"{row.get('bestSplitVehicleCount')} | {row.get('setPartitioningProducedSolution')} | {row.get('runtimeMs')} | {row.get('blockers')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 18 time-window restructuring gate.")
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--time-limit-ms", type=int, default=15_000)
    args = parser.parse_args(argv)
    report = build_report(Path(args.candidate_dir), args.time_limit_ms)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase18_time_window_restructuring_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase18_time_window_restructuring_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE18 TIME WINDOW RESTRUCTURING GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

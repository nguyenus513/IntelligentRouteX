from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

TARGETS = {("solomon", "RC101"), ("li-lim", "LR101"), ("li-lim", "LRC101")}
HARD_KEYS = ("capacityViolationCount", "timeWindowViolationCount", "pickupBeforeDropoffViolationCount", "vehicleLimitViolationCount")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def load_rows(root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(root.rglob("external_benchmark_results.json")):
        payload = read_json(path)
        for row in payload.get("results", []):
            if row.get("solver") != "our-dispatch-v2":
                continue
            key = (str(row.get("suite", "")), str(row.get("instance", "")))
            if key in TARGETS:
                enriched = dict(row)
                enriched["artifactPath"] = str(path)
                enriched["solution"] = read_solution(enriched)
                rows[key] = enriched
    return rows


def read_solution(row: dict[str, Any]) -> dict[str, Any]:
    solution_path = row.get("solutionPath")
    if not solution_path:
        return {}
    path = Path(str(solution_path))
    if not path.exists():
        return {}
    return read_json(path)


def hard_violation_count(row: dict[str, Any]) -> int:
    return sum(int(number(row.get(key))) for key in HARD_KEYS)


def vehicle_gap(row: dict[str, Any]) -> int | None:
    vehicle_count = row.get("vehicleCount")
    best = row.get("bestKnownVehicleCount")
    if vehicle_count is None or best is None:
        return None
    return max(0, int(number(vehicle_count)) - int(number(best)))


def consolidation_trace(solution: dict[str, Any]) -> dict[str, Any]:
    value = solution.get("globalConsolidation")
    return value if isinstance(value, dict) else {}


def summarize_target(key: tuple[str, str], baseline: dict[str, Any] | None, candidate: dict[str, Any] | None, time_limit_ms: int) -> dict[str, Any]:
    blockers: list[str] = []
    if candidate is None:
        return {"suite": key[0], "instance": key[1], "blockers": ["phase10-target-missing"], "pass": False}
    baseline_gap = vehicle_gap(baseline or {})
    candidate_gap = vehicle_gap(candidate)
    hard_count = hard_violation_count(candidate)
    trace = consolidation_trace(candidate.get("solution", {}))
    accepted_moves = int(number(trace.get("acceptedMoves"))) if trace else 0
    operator_attempts = int(number(trace.get("operatorAttempts"))) if trace else 0
    gap_delta = None if baseline_gap is None or candidate_gap is None else baseline_gap - candidate_gap

    if not bool(candidate.get("feasible", False)):
        blockers.append("phase10-infeasible-target")
    if hard_count > 0:
        blockers.append("phase10-hard-violation")
    if number(candidate.get("runtimeMs")) > time_limit_ms:
        blockers.append("phase10-runtime-timeout")
    if candidate_gap is None:
        blockers.append("phase10-gap-not-measured")
    if gap_delta is not None and gap_delta < 0:
        blockers.append("phase10-gap-regressed")
    if not trace:
        blockers.append("phase10-no-improvement-trace")
    elif operator_attempts <= 0 and (candidate_gap or 0) > 0:
        blockers.append("phase10-no-improvement-trace")

    return {
        "suite": key[0],
        "instance": key[1],
        "baselineVehicleCount": None if baseline is None else baseline.get("vehicleCount"),
        "candidateVehicleCount": candidate.get("vehicleCount"),
        "bestKnownVehicleCount": candidate.get("bestKnownVehicleCount"),
        "baselineGap": baseline_gap,
        "candidateGap": candidate_gap,
        "gapDelta": gap_delta,
        "baselineDistance": None if baseline is None else baseline.get("totalDistance"),
        "candidateDistance": candidate.get("totalDistance"),
        "runtimeMs": number(candidate.get("runtimeMs")),
        "verdict": candidate.get("verdict"),
        "hardViolationCount": hard_count,
        "tracePresent": bool(trace),
        "acceptedMoves": accepted_moves,
        "operatorAttempts": operator_attempts,
        "topRejectReasons": trace.get("topRejectReasons", {}) if trace else {},
        "solutionPath": candidate.get("solutionPath", ""),
        "blockers": blockers,
        "pass": not blockers,
    }


def build_report(baseline_dir: Path, candidate_dir: Path, time_limit_ms: int) -> dict[str, Any]:
    baseline_rows = load_rows(baseline_dir)
    candidate_rows = load_rows(candidate_dir)
    rows = [summarize_target(key, baseline_rows.get(key), candidate_rows.get(key), time_limit_ms) for key in sorted(TARGETS)]
    blockers = [blocker for row in rows for blocker in row.get("blockers", [])]
    measured = [row for row in rows if row.get("candidateGap") is not None]
    baseline_gap_sum = sum(int(row.get("baselineGap") or 0) for row in measured)
    candidate_gap_sum = sum(int(row.get("candidateGap") or 0) for row in measured)
    total_gap_delta = baseline_gap_sum - candidate_gap_sum
    verdict = "PASS" if not blockers and total_gap_delta > 0 else "PASS_WITH_LIMITS" if not any(b in blockers for b in ["phase10-infeasible-target", "phase10-hard-violation", "phase10-runtime-timeout", "phase10-gap-regressed", "phase10-target-missing", "phase10-no-improvement-trace"]) else "FAIL"
    return {
        "schemaVersion": "phase10-gap-reduction-gate/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "baselineDir": str(baseline_dir),
        "candidateDir": str(candidate_dir),
        "rowCount": len(rows),
        "baselineGapSum": baseline_gap_sum,
        "candidateGapSum": candidate_gap_sum,
        "totalGapDelta": total_gap_delta,
        "rows": rows,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 10 Gap Reduction Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- rows: `{report['rowCount']}`",
        f"- baseline gap sum: `{report['baselineGapSum']}`",
        f"- candidate gap sum: `{report['candidateGapSum']}`",
        f"- total gap delta: `{report['totalGapDelta']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Gap B/C | Vehicles B/C/BKS | Runtime | Trace | Accepted | Attempts | Reject Reasons | Blockers |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('baselineGap')}/{row.get('candidateGap')} | "
            f"{row.get('baselineVehicleCount')}/{row.get('candidateVehicleCount')}/{row.get('bestKnownVehicleCount')} | "
            f"{row.get('runtimeMs')} | {row.get('tracePresent')} | {row.get('acceptedMoves')} | {row.get('operatorAttempts')} | "
            f"{row.get('topRejectReasons')} | {row.get('blockers')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 10 vehicle-gap reduction gate.")
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--time-limit-ms", type=int, default=15_000)
    args = parser.parse_args(argv)
    report = build_report(Path(args.baseline_dir), Path(args.candidate_dir), args.time_limit_ms)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase10_gap_reduction_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase10_gap_reduction_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE10 GAP GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


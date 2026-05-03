from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REQUIRED_SUITES = {"solomon", "li-lim"}
HARD_VIOLATION_KEYS = (
    "capacityViolationCount",
    "timeWindowViolationCount",
    "pickupBeforeDropoffViolationCount",
    "vehicleLimitViolationCount",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def number(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def load_rows(input_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(input_dir.rglob("external_benchmark_results.json")):
        payload = read_json(path)
        for row in payload.get("results", []):
            enriched = dict(row)
            enriched["artifactPath"] = str(path)
            enriched["suiteSolver"] = f"{row.get('suite')}/{row.get('solver')}"
            rows.append(enriched)
    return rows


def hard_violation_count(row: dict[str, Any]) -> int:
    return sum(int(number(row, key)) for key in HARD_VIOLATION_KEYS)


def row_blockers(row: dict[str, Any], time_limit_ms: int, require_best_known: bool) -> list[str]:
    blockers: list[str] = []
    solver = str(row.get("solver", ""))
    verdict = str(row.get("verdict", ""))
    if solver != "our-dispatch-v2":
        return blockers
    if verdict == "EVIDENCE_GAP":
        blockers.append("community-our-dispatch-evidence-gap")
    if verdict == "FAIL":
        blockers.append("community-benchmark-fail-verdict")
    if bool(row.get("feasible", False)) is False and verdict != "EVIDENCE_GAP":
        blockers.append("community-benchmark-infeasible")
    if hard_violation_count(row) > 0:
        blockers.append("community-benchmark-hard-violation")
    if number(row, "runtimeMs") > time_limit_ms:
        blockers.append("community-benchmark-runtime-timeout")
    if require_best_known and verdict == "PASS_WITH_LIMITS":
        blockers.append("community-benchmark-above-best-known")
    return blockers


def summarize(input_dir: Path, time_limit_ms: int, require_best_known: bool) -> dict[str, Any]:
    rows = load_rows(input_dir)
    suites = {str(row.get("suite", "")) for row in rows if row.get("solver") == "our-dispatch-v2"}
    blockers: list[str] = []
    if not rows:
        blockers.append("community-benchmark-no-artifacts")
    missing_suites = sorted(REQUIRED_SUITES - suites)
    blockers.extend(f"community-benchmark-missing-suite-{suite}" for suite in missing_suites)

    row_summaries: list[dict[str, Any]] = []
    for row in rows:
        blockers_for_row = row_blockers(row, time_limit_ms, require_best_known)
        blockers.extend(blockers_for_row)
        row_summaries.append({
            "suite": row.get("suite"),
            "instance": row.get("instance"),
            "solver": row.get("solver"),
            "implementation": row.get("solverImplementation", ""),
            "dataSource": row.get("effectiveDataSource", row.get("dataSource", "")),
            "feasible": bool(row.get("feasible", False)),
            "vehicleCount": row.get("vehicleCount"),
            "bestKnownVehicleCount": row.get("bestKnownVehicleCount"),
            "totalDistance": number(row, "totalDistance"),
            "bestKnownDistance": row.get("bestKnownDistance"),
            "objectiveGapPercent": row.get("objectiveGapPercent"),
            "runtimeMs": number(row, "runtimeMs"),
            "verdict": row.get("verdict"),
            "verdictReasons": row.get("verdictReasons", []),
            "hardViolationCount": hard_violation_count(row),
            "blockers": blockers_for_row,
            "artifactPath": row.get("artifactPath"),
        })

    verdict_counts = Counter(str(row.get("verdict", "")) for row in rows)
    our_rows = [row for row in row_summaries if row["solver"] == "our-dispatch-v2"]
    return {
        "schemaVersion": "community-benchmark-phase-gate/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "inputDir": str(input_dir),
        "rowCount": len(rows),
        "ourDispatchRowCount": len(our_rows),
        "suites": sorted(suites),
        "verdictCounts": dict(sorted(verdict_counts.items())),
        "feasibleRows": sum(1 for row in rows if row.get("feasible")),
        "passWithLimitsRows": sum(1 for row in rows if row.get("verdict") == "PASS_WITH_LIMITS"),
        "maxRuntimeMs": max((row["runtimeMs"] for row in row_summaries), default=0.0),
        "maxObjectiveGapPercent": max((number(row, "objectiveGapPercent") for row in rows), default=0.0),
        "rows": row_summaries,
        "blockers": blockers,
        "pass": bool(rows) and not blockers,
    }


def markdown(report: dict[str, Any]) -> str:
    verdict = "PASS" if report["pass"] else "FAIL"
    lines = [
        "# Community Benchmark Phase Gate",
        "",
        f"- verdict: `{verdict}`",
        f"- rows: `{report['rowCount']}`",
        f"- our-dispatch rows: `{report['ourDispatchRowCount']}`",
        f"- suites: `{report['suites']}`",
        f"- verdict counts: `{report['verdictCounts']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Solver | Feasible | Vehicles | BKS Vehicles | Gap % | Runtime ms | Verdict | Blockers |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['suite']} | {row['instance']} | {row['solver']} | {row['feasible']} | "
            f"{row['vehicleCount']} | {row['bestKnownVehicleCount']} | {row['objectiveGapPercent']} | "
            f"{row['runtimeMs']} | {row['verdict']} | {row['blockers']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 8 community benchmark gate.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--time-limit-ms", type=int, default=30_000)
    parser.add_argument("--require-best-known", action="store_true")
    args = parser.parse_args(argv)

    report = summarize(Path(args.input_dir), args.time_limit_ms, args.require_best_known)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "community_benchmark_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "community_benchmark_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[COMMUNITY BENCHMARK GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


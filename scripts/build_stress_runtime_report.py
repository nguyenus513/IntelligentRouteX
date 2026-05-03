from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def as_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def load_rows(input_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("dispatch-quality-*-legacy-v2-controlled-*.json")):
        if "compare" in path.name:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        selector = payload.get("selectorTelemetry") if isinstance(payload.get("selectorTelemetry"), dict) else {}
        repair = payload.get("activeRepair") if isinstance(payload.get("activeRepair"), dict) else {}
        fallback = payload.get("stageFallbackSummary") if isinstance(payload.get("stageFallbackSummary"), dict) else {}
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        row = {
            "file": path.name,
            "scenarioPack": payload.get("scenarioPack", "unknown"),
            "workloadSize": payload.get("workloadSize", "unknown"),
            "baselineId": payload.get("baselineId", "unknown"),
            "selectorTimedOut": as_bool(selector.get("timedOut")),
            "selectorFallbackLevel": str(selector.get("fallbackLevel", "NONE")),
            "selectorPoolInputCount": as_int(selector.get("poolInputCount")),
            "selectorPoolReducedCount": as_int(selector.get("poolReducedCount")),
            "selectorPoolRejectedCount": as_int(selector.get("poolRejectedCount")),
            "selectorPoolCapApplied": as_bool(selector.get("selectorPoolCapApplied")),
            "selectorPoolCapObjectiveLoss": as_float(selector.get("selectorPoolCapObjectiveLoss")),
            "repairTimedOut": as_bool(repair.get("timedOut")),
            "repairRuntimeMs": as_int(repair.get("runtimeMs")),
            "repairOperatorsTried": as_int(repair.get("operatorsTried")),
            "totalFallbacks": as_int(fallback.get("totalFallbacks")),
            "selectedProposalCount": as_int(metrics.get("selectedProposalCount")),
            "executedAssignmentCount": as_int(metrics.get("executedAssignmentCount")),
        }
        row["runtimeClean"] = not (
            row["selectorTimedOut"]
            or row["repairTimedOut"]
            or row["totalFallbacks"] > 0
            or row["selectorPoolCapObjectiveLoss"] > 0.0
        )
        rows.append(row)
    return rows


def summarize(rows: list[dict[str, Any]], expected: list[str]) -> dict[str, Any]:
    scenario_counts = Counter(row["scenarioPack"] for row in rows)
    size_counts = Counter(row["workloadSize"] for row in rows)
    bad_rows = [row for row in rows if not row["runtimeClean"]]
    missing_expected = [scenario for scenario in expected if scenario not in scenario_counts]
    return {
        "schemaVersion": "stress-runtime-report/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "rowCount": len(rows),
        "scenarioCounts": dict(sorted(scenario_counts.items())),
        "sizeCounts": dict(sorted(size_counts.items())),
        "missingExpectedScenarios": missing_expected,
        "selectorTimeoutCount": sum(1 for row in rows if row["selectorTimedOut"]),
        "repairTimeoutCount": sum(1 for row in rows if row["repairTimedOut"]),
        "fallbackRowCount": sum(1 for row in rows if row["totalFallbacks"] > 0),
        "poolCapLossRowCount": sum(1 for row in rows if row["selectorPoolCapObjectiveLoss"] > 0.0),
        "maxSelectorPoolInputCount": max((row["selectorPoolInputCount"] for row in rows), default=0),
        "maxRepairRuntimeMs": max((row["repairRuntimeMs"] for row in rows), default=0),
        "badRows": bad_rows,
        "rows": rows,
        "pass": not bad_rows,
        "passWithLimits": not bad_rows and bool(missing_expected),
    }


def markdown(report: dict[str, Any]) -> str:
    verdict = "PASS" if report["pass"] and not report["passWithLimits"] else "PASS_WITH_LIMITS" if report["pass"] else "FAIL"
    lines = [
        "# Stress Runtime Report",
        "",
        f"- verdict: `{verdict}`",
        f"- rows: `{report['rowCount']}`",
        f"- selector timeouts: `{report['selectorTimeoutCount']}`",
        f"- repair timeouts: `{report['repairTimeoutCount']}`",
        f"- fallback rows: `{report['fallbackRowCount']}`",
        f"- pool cap loss rows: `{report['poolCapLossRowCount']}`",
        f"- missing expected scenarios: `{report['missingExpectedScenarios']}`",
        "",
        "## Scenario Counts",
        "",
    ]
    for scenario, count in report["scenarioCounts"].items():
        lines.append(f"- `{scenario}`: `{count}`")
    lines.extend(["", "## Runtime Rows", "", "| Scenario | Size | Baseline | Selector Timeout | Repair Timeout | Fallbacks | Cap Loss | Pool |", "|---|---|---|---:|---:|---:|---:|---|"])
    for row in report["rows"]:
        lines.append(
            f"| {row['scenarioPack']} | {row['workloadSize']} | {row['baselineId']} | {row['selectorTimedOut']} | "
            f"{row['repairTimedOut']} | {row['totalFallbacks']} | {row['selectorPoolCapObjectiveLoss']} | "
            f"{row['selectorPoolInputCount']}/{row['selectorPoolReducedCount']}/{row['selectorPoolRejectedCount']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build stress runtime telemetry report from dispatch-quality artifacts.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-scenario", action="append", default=[])
    args = parser.parse_args(argv)
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    rows = load_rows(input_dir)
    report = summarize(rows, args.expected_scenario)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stress_runtime_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "stress_runtime_report.md").write_text(markdown(report), encoding="utf-8")
    print(f"[STRESS REPORT] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

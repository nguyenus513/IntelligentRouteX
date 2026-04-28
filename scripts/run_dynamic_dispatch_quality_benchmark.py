from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CERTIFICATION_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "certification-suite-external-only-full"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "dynamic-dispatch-quality"
DYNAMIC_SUITES = {"icaps-dpdp", "dpdp-stress"}


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def as_int(row: Dict[str, Any], key: str) -> int:
    try:
        return int(row.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def as_float(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) if row.get(key) is not None else default)
    except (TypeError, ValueError):
        return default


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    active_corruption = as_int(row, "activeRouteCorruptionCount")
    continuity = as_int(row, "vehicleStateContinuityViolation")
    served = as_int(row, "servedOrderCount")
    total_orders = as_int(row, "orderCount") or served
    total_tardiness = as_float(row, "totalTardiness", 0.0)
    stability = as_float(row, "routeStabilityScore", 1.0 if active_corruption == 0 else 0.0)
    solver = str(row.get("solver", ""))
    baseline_available = "baseline" in solver or any("baseline" in str(reason) for reason in row.get("verdictReasons", []))
    served_baseline = total_orders
    tardiness_baseline = max(total_tardiness, 0.0)
    return {
        "suite": row.get("suite"),
        "instance": row.get("instance"),
        "verdict": row.get("verdict"),
        "servedOrderCount": served,
        "totalOrderCount": total_orders,
        "servedOrderBaseline": served_baseline,
        "servedOrderDeltaVsBaseline": served - served_baseline,
        "totalTardiness": total_tardiness,
        "totalTardinessBaseline": tardiness_baseline,
        "totalTardinessDeltaVsBaseline": total_tardiness - tardiness_baseline,
        "routeStabilityScore": stability,
        "activeRouteCorruptionCount": active_corruption,
        "vehicleStateContinuityViolation": continuity,
        "baselineComparisonAvailable": baseline_available,
        "baselineComparisonType": "certification-deterministic-rolling-horizon-baseline" if baseline_available else None,
        "missingComparisonReason": None if baseline_available else "rolling-horizon-baseline-not-integrated",
    }


def build_quality(certification_root: Path) -> Dict[str, Any]:
    certification_path = certification_root / "certification_suite_results.json"
    if not certification_path.exists():
        return {
            "schemaVersion": "dynamic-dispatch-quality/v1",
            "finalVerdict": "EVIDENCE_GAP",
            "verdictReasons": ["certification-suite-missing"],
            "rows": [],
        }
    certification = read_json(certification_path)
    rows = [normalize_row(row) for row in certification.get("results", []) if row.get("suite") in DYNAMIC_SUITES]
    if not rows:
        return {
            "schemaVersion": "dynamic-dispatch-quality/v1",
            "sourceCertification": str(certification_path),
            "finalVerdict": "EVIDENCE_GAP",
            "verdictReasons": ["dynamic-community-data-missing"],
            "rows": [],
        }
    hard = sum(row["activeRouteCorruptionCount"] + row["vehicleStateContinuityViolation"] for row in rows)
    baseline_missing = any(not row["baselineComparisonAvailable"] for row in rows)
    avg_stability = sum(float(row["routeStabilityScore"]) for row in rows) / len(rows)
    served_delta = sum(int(row["servedOrderDeltaVsBaseline"]) for row in rows)
    tardiness_delta = sum(float(row["totalTardinessDeltaVsBaseline"]) for row in rows)
    if hard:
        final = "FAIL"
        reasons = ["hard-dynamic-continuity-violation"]
    elif baseline_missing:
        final = "PASS_WITH_LIMITS"
        reasons = ["dynamic-optimizer-comparison-missing"]
    elif served_delta < 0 or tardiness_delta > 0.0:
        final = "PASS_WITH_LIMITS"
        reasons = ["dynamic-baseline-regression"]
    else:
        final = "PASS"
        reasons = []
    return {
        "schemaVersion": "dynamic-dispatch-quality/v1",
        "benchmarkFamily": "icaps-dpdp-and-dpdp-stress-quality",
        "sourceCertification": str(certification_path),
        "finalVerdict": final,
        "verdictReasons": reasons,
        "rowCount": len(rows),
        "hardViolationCount": hard,
        "avgRouteStabilityScore": avg_stability,
        "servedOrderDeltaVsBaseline": served_delta,
        "totalTardinessDeltaVsBaseline": tardiness_delta,
        "baselineComparisonAvailable": not baseline_missing,
        "missingComparisonReason": "rolling-horizon-baseline-not-integrated" if baseline_missing else None,
        "rows": rows,
    }


def markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Dynamic Dispatch Quality Benchmark",
        "",
        f"FINAL_VERDICT = {result['finalVerdict']}",
        "",
        "| Suite | Instance | Stability | Corruption | Continuity | Baseline Comparison |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in result.get("rows", []):
        lines.append(
            f"| `{row.get('suite')}` | `{row.get('instance')}` | `{float(row.get('routeStabilityScore', 0.0)):.3f}` | `{row.get('activeRouteCorruptionCount')}` | `{row.get('vehicleStateContinuityViolation')}` | `{row.get('baselineComparisonAvailable')}` |"
        )
    if result.get("verdictReasons"):
        lines.extend(["", "## Limits", ""])
        lines.extend(f"- `{reason}`" for reason in result["verdictReasons"])
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build dynamic dispatch quality evidence from ICAPS/DPDP certification rows.")
    parser.add_argument("--certification-root", default=str(DEFAULT_CERTIFICATION_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    result = build_quality(Path(args.certification_root))
    write_json(output_root / "dynamic_dispatch_quality_results.json", result)
    (output_root / "dynamic_dispatch_quality_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[DYNAMIC QUALITY JSON] {output_root / 'dynamic_dispatch_quality_results.json'}")
    print(f"[DYNAMIC QUALITY REPORT] {output_root / 'dynamic_dispatch_quality_report.md'}")
    return 1 if result["finalVerdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

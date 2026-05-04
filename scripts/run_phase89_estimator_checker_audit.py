from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from optimizer.phase88_route_schedule_cache import RouteScheduleCache
from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan
from run_phase84_unified_intelligent_optimizer import run as run_phase84


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase89_estimator_checker_audit_v1"


def normalize_violation(violation: str) -> str:
    mapping = {
        "missing-required-nodes": "missing-request",
        "duplicate-required-nodes": "duplicate-request",
        "pickup-before-dropoff-violation": "pickup-after-dropoff",
        "capacity-violation": "capacity-overflow",
        "time-window-violation": "time-window-late",
        "route-does-not-start-end-at-depot": "invalid-route-shape",
        "unknown-node-in-route": "invalid-route-shape",
        "vehicle-count-violation": "invalid-route-shape",
        "active-route-lock-violation": "active-lock-violation",
    }
    return mapping.get(str(violation), "unknown")


def classify_alignment(trace: Dict[str, Any]) -> str:
    estimator = trace.get("estimator", {}) or {}
    checker = trace.get("fullChecker", {}) or {}
    lock = trace.get("lockValidator", {}) or {}
    violations = [normalize_violation(item) for item in checker.get("violations", [])]
    if checker.get("feasible") and trace.get("rejectReason") == "objective-not-improved":
        return "objective-not-reached-no-feasible"
    if not lock.get("valid", True):
        return "estimator-too-loose-lock"
    if "capacity-overflow" in violations:
        return "estimator-too-loose-capacity"
    if "time-window-late" in violations:
        return "estimator-too-loose-time-window"
    if "invalid-route-shape" in violations:
        return "route-structure-invalid"
    if "missing-request" in violations or "duplicate-request" in violations or "pickup-after-dropoff" in violations:
        return "pickup-dropoff-coverage-invalid"
    if checker.get("feasible"):
        return "checker-estimator-aligned"
    return "unknown"


def classify_pruned(sample: Dict[str, Any]) -> str:
    reason = str(sample.get("pruneReason"))
    if reason == "capacity":
        return "estimator-too-strict-capacity"
    if reason == "timeWindow":
        return "estimator-too-strict-time-window"
    if reason == "lock":
        return "estimator-too-strict-lock"
    return "unknown"


def schedule_semantic_diff(route: List[str], instance: Dict[str, Any]) -> Dict[str, Any]:
    schedule = RouteScheduleCache().build(instance, route)
    service_mismatch = any(departure < start for start, departure in zip(schedule.serviceStartTimes, schedule.departureTimes))
    return {"route": route, "serviceTimeMismatch": service_mismatch, "timeWindowRisk": schedule.timeWindowRisk, "capacityPeak": schedule.capacityPeak, "arrivalCount": len(schedule.arrivalTimes)}


def count_by(rows: List[Dict[str, Any]], key: str = "classification") -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    traces: List[Dict[str, Any]] = []
    pruned: List[Dict[str, Any]] = []
    semantic_rows: List[Dict[str, Any]] = []
    skipped = []
    for suite in [part.strip() for part in args.suites.split(",") if part.strip()]:
        try:
            phase84_args = Namespace(suite=suite, vroom_url="", time_limit=args.time_limit, max_instances_per_suite=args.max_instances_per_suite, output_dir=str(output_dir / "per_suite" / suite.replace("-", "_")))
            summary = run_phase84(phase84_args)
            for row in summary.get("rows", []):
                for trace in row.get("checkedCandidateTraces", []):
                    traces.append({**trace, "instance": row.get("instance"), "classification": classify_alignment(trace)})
                for sample in row.get("prunedCandidateSamples", [])[: args.sample_pruned]:
                    pruned.append({**sample, "instance": row.get("instance"), "classification": classify_pruned(sample)})
        except Exception as exception:  # pragma: no cover
            skipped.append({"suite": suite, "reason": str(exception)})
    alignment = {"schemaVersion": "phase89-alignment-classification/v1", "rows": traces + pruned, "classificationCounts": count_by(traces + pruned)}
    violation_rows = []
    for trace in traces:
        for violation in trace.get("fullChecker", {}).get("violations", []):
            violation_rows.append({"instance": trace.get("instance"), "rawViolation": violation, "normalized": normalize_violation(violation)})
    for trace in traces[:20]:
        route = (trace.get("candidateRoute") or [])
        if route:
            semantic_rows.append({"instance": trace.get("instance"), **schedule_semantic_diff(route, {})})
    anti = antihardcode_scan()
    unknown_count = alignment["classificationCounts"].get("unknown", 0) + sum(1 for row in violation_rows if row.get("normalized") == "unknown")
    too_small = len(traces) + len(pruned) == 0
    gate = "FAIL" if unknown_count or anti.get("gate") != "PASS" else "PASS_WITH_LIMITS" if too_small or skipped else "PASS"
    summary = {"schemaVersion": "phase89-estimator-checker-audit/v1", "gate": gate, "productionMainReady": False, "antiHardcodeGate": anti.get("gate"), "checkedCandidateCount": len(traces), "prunedSampleCount": len(pruned), "unknownCount": unknown_count, "skippedSuites": skipped, "classificationCounts": alignment["classificationCounts"]}
    write_json(output_dir / "phase89_summary.json", summary)
    write_json(output_dir / "checked_candidate_traces.json", {"rows": traces})
    write_json(output_dir / "pruned_candidate_samples.json", {"rows": pruned})
    write_json(output_dir / "alignment_classification.json", alignment)
    write_json(output_dir / "checker_violation_summary.json", {"rows": violation_rows, "classificationCounts": count_by(violation_rows, "normalized")})
    write_json(output_dir / "schedule_semantic_diff.json", {"rows": semantic_rows})
    (output_dir / "phase89_summary.md").write_text(markdown(summary), encoding="utf-8")
    (output_dir / "recommendations.md").write_text(recommendations(alignment["classificationCounts"]), encoding="utf-8")
    return summary


def recommendations(counts: Dict[str, int]) -> str:
    lines = ["# Phase 89 Recommendations", ""]
    if counts.get("estimator-too-strict-time-window"):
        lines.append("- Relax schedule estimate to match checker waiting/service semantics.")
    if counts.get("estimator-too-loose-time-window"):
        lines.append("- Tighten insertion time-window feasibility or add repair before full check.")
    if counts.get("pickup-dropoff-coverage-invalid"):
        lines.append("- Fix candidate construction and route shape normalization.")
    if counts.get("checker-estimator-aligned"):
        lines.append("- Estimator/checker align; stronger repair/ejection may be needed.")
    return "\n".join(lines) + "\n"


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 89 Estimator/Checker Alignment Audit",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Checked candidates: `{summary.get('checkedCandidateCount')}`",
        f"- Pruned samples: `{summary.get('prunedSampleCount')}`",
        f"- Unknown count: `{summary.get('unknownCount')}`",
        f"- Classifications: `{json.dumps(summary.get('classificationCounts', {}), sort_keys=True)}`",
        "",
        "Phase 89 is diagnostic only and does not claim `PRODUCTION_MAIN_READY`.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 89 estimator/checker alignment audit.")
    parser.add_argument("--suites", default="vroom-capability-full")
    parser.add_argument("--max-instances-per-suite", type=int, default=5)
    parser.add_argument("--sample-pruned", type=int, default=10)
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE89 ESTIMATOR CHECKER AUDIT] wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan
from run_phase84_unified_intelligent_optimizer import run as run_phase84


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase86_operator_roi_audit_v1"


def classify_rejection(reason: str, vehicle_delta: float = 0.0, distance_delta: float = 0.0, objective_delta: float = 0.0) -> str:
    if reason == "generation-too-narrow":
        return "generation-too-narrow"
    if reason == "pruning-too-aggressive":
        return "pruning-too-aggressive"
    if reason == "feasibility-blocked":
        return "feasibility-blocked"
    if reason == "objective-not-improved":
        if distance_delta < 0 and objective_delta >= 0:
            return "distance-improved-but-objective-rejected"
        if vehicle_delta > 0:
            return "vehicle-regression-rejected"
        return "no-quality-improvement"
    if reason == "hard-violation":
        return "hard-violation-rejected"
    if reason == "lock-violation":
        return "lock-churn-regression-rejected"
    if reason == "candidate-cap":
        return "candidate-cap"
    if reason == "runtime-cap":
        return "runtime-cap"
    return "unknown"


def recommendation_engine(operator_rows: List[Dict[str, Any]], calibration_counts: Dict[str, int]) -> List[str]:
    recommendations = []
    generated_total = sum(int(row.get("generatedCandidates", 0) or 0) for row in operator_rows)
    zero_generated = sum(1 for row in operator_rows if int(row.get("generatedCandidates", 0) or 0) == 0)
    feasible_total = sum(int(row.get("feasibleCandidates", 0) or 0) for row in operator_rows)
    accepted_total = sum(int(row.get("acceptedCandidates", 0) or 0) for row in operator_rows)
    if generated_total == 0 or zero_generated > max(0, len(operator_rows) // 2):
        recommendations.append("candidate generation is too narrow or not wired")
    if feasible_total > 0 and accepted_total == 0:
        recommendations.append("objective/acceptance audit needed: feasible candidates exist but none accepted")
    if calibration_counts.get("distance-improved-but-objective-rejected", 0) > 0:
        recommendations.append("consider objective weight calibration while keeping one code path")
    if calibration_counts.get("hard-violation-rejected", 0) > calibration_counts.get("no-quality-improvement", 0):
        recommendations.append("prioritize feasibility-preserving insertion and incremental checks")
    if calibration_counts.get("candidate-cap", 0) > 0:
        recommendations.append("improve candidate ordering/pruning before increasing caps")
    return recommendations or ["operator audit complete; scale operators with highest feasible candidate rate"]


def flatten_phase84(summary: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    operator_rows: List[Dict[str, Any]] = []
    samples: List[Dict[str, Any]] = []
    feature_rows: List[Dict[str, Any]] = []
    for row in summary.get("rows", []):
        feature_rows.append({"instance": row.get("instance"), "source": row.get("source"), "hardViolations": row.get("hardViolations"), "distance": row.get("distance")})
        for telemetry in row.get("operatorTelemetry", {}).values():
            pass
        for budget in row.get("budgetTelemetry", []):
            fail_reasons = budget.get("failReasons") or {}
            operator = budget.get("operator")
            operator_rows.append(
                {
                    "instance": row.get("instance"),
                    "source": row.get("source"),
                    "operator": operator,
                    "attempts": 1 if int(budget.get("candidateChecks", 0) or 0) or int(budget.get("generatedCandidates", 0) or 0) else 0,
                    "generatedCandidates": budget.get("generatedCandidates", 0),
                    "candidateChecks": budget.get("candidateChecks", 0),
                    "generatedMoves": budget.get("generatedCandidates", 0),
                    "rankedMoves": budget.get("generatedCandidates", 0),
                    "prunedMoves": max(0, int(budget.get("generatedCandidates", 0) or 0) - int(budget.get("candidateChecks", 0) or 0)),
                    "feasibleCandidates": budget.get("feasibleCandidateCount", 0),
                    "acceptedCandidates": budget.get("acceptedCount", 0),
                    "objectiveNotImproved": fail_reasons.get("objective-not-improved", 0),
                    "hardViolation": fail_reasons.get("hard-violation", 0),
                    "lockViolation": fail_reasons.get("lock-violation", 0),
                    "candidateCap": fail_reasons.get("candidate-cap", 0),
                    "runtimeCap": fail_reasons.get("runtime-cap", 0),
                    "bestCandidateDistanceDelta": None,
                    "bestCandidateObjectiveDelta": None,
                    "bestCandidateVehicleDelta": None,
                    "meanRuntimeMs": budget.get("usedMs", 0),
                    "roi": budget.get("roi", 0.0),
                    "failReasons": fail_reasons,
                }
            )
            if int(budget.get("generatedCandidates", 0) or 0) == 0:
                samples.append({"operator": operator, "rejectReason": "generation-too-narrow", "classification": "generation-too-narrow", "sampleIndex": 0, "instance": row.get("instance")})
            elif int(budget.get("candidateChecks", 0) or 0) == 0:
                samples.append({"operator": operator, "rejectReason": "pruning-too-aggressive", "classification": "pruning-too-aggressive", "sampleIndex": 0, "instance": row.get("instance")})
            elif int(budget.get("feasibleCandidateCount", 0) or 0) == 0 and int(budget.get("candidateChecks", 0) or 0) > 0:
                samples.append({"operator": operator, "rejectReason": "feasibility-blocked", "classification": "feasibility-blocked", "sampleIndex": 0, "instance": row.get("instance")})
            for reason, count in fail_reasons.items():
                for index in range(min(3, int(count or 0))):
                    samples.append({"operator": operator, "rejectReason": reason, "classification": classify_rejection(str(reason)), "sampleIndex": index, "instance": row.get("instance")})
    return operator_rows, samples, feature_rows


def aggregate_calibration(samples: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for sample in samples:
        classification = str(sample.get("classification", "unknown"))
        counts[classification] = counts.get(classification, 0) + 1
    return counts


def feature_correlation(feature_rows: List[Dict[str, Any]], operator_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_instance = {str(row.get("instance")): row for row in feature_rows}
    rows = []
    for operator in operator_rows:
        feature = by_instance.get(str(operator.get("instance")), {})
        rows.append({"instance": operator.get("instance"), "operator": operator.get("operator"), "source": feature.get("source"), "generatedCandidates": operator.get("generatedCandidates"), "acceptedCandidates": operator.get("acceptedCandidates")})
    return {"schemaVersion": "phase86-feature-correlation/v1", "rows": rows}


def run(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_operator_rows: List[Dict[str, Any]] = []
    all_samples: List[Dict[str, Any]] = []
    all_features: List[Dict[str, Any]] = []
    skipped = []
    for suite in [part.strip() for part in args.suites.split(",") if part.strip()]:
        try:
            phase84_args = Namespace(suite=suite, vroom_url="", time_limit=args.time_limit, max_instances_per_suite=args.max_instances_per_suite, output_dir=str(output_dir / "per_suite" / suite.replace("-", "_")))
            phase84_summary = run_phase84(phase84_args)
            operator_rows, samples, features = flatten_phase84(phase84_summary)
            all_operator_rows.extend(operator_rows)
            all_samples.extend(samples)
            all_features.extend(features)
        except Exception as exception:  # pragma: no cover - audit must report skipped suites.
            skipped.append({"suite": suite, "reason": str(exception)})
    calibration_counts = aggregate_calibration(all_samples)
    recommendations = recommendation_engine(all_operator_rows, calibration_counts)
    anti = antihardcode_scan()
    unknown = calibration_counts.get("unknown", 0)
    gate = "FAIL" if unknown or anti.get("gate") != "PASS" else "PASS_WITH_LIMITS" if skipped else "PASS"
    summary = {"schemaVersion": "phase86-operator-roi-audit/v1", "gate": gate, "productionMainReady": False, "antiHardcodeGate": anti.get("gate"), "skippedSuites": skipped, "operatorCount": len(all_operator_rows), "rejectionCounts": calibration_counts, "recommendations": recommendations}
    write_json(output_dir / "phase86_summary.json", summary)
    write_json(output_dir / "operator_roi_deep.json", {"rows": all_operator_rows})
    write_json(output_dir / "rejected_candidate_samples.json", {"rows": all_samples})
    write_json(output_dir / "objective_calibration.json", {"classificationCounts": calibration_counts})
    write_json(output_dir / "feature_correlation.json", feature_correlation(all_features, all_operator_rows))
    (output_dir / "phase86_summary.md").write_text(markdown(summary), encoding="utf-8")
    (output_dir / "recommendations.md").write_text("# Phase 86 Recommendations\n\n" + "\n".join(f"- {item}" for item in recommendations) + "\n", encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 86 Operator ROI Audit",
        "",
        f"- Gate: **{summary.get('gate')}**",
        f"- Anti-hardcode: `{summary.get('antiHardcodeGate')}`",
        f"- Rejections: `{json.dumps(summary.get('rejectionCounts', {}), sort_keys=True)}`",
        f"- Recommendations: `{json.dumps(summary.get('recommendations', []), sort_keys=True)}`",
        "",
        "Phase 86 is diagnostic only and does not claim `PRODUCTION_MAIN_READY`.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 86 operator ROI audit.")
    parser.add_argument("--suites", default="vroom-capability-full")
    parser.add_argument("--max-instances-per-suite", type=int, default=5)
    parser.add_argument("--time-limit", default="30s")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args)
    print(f"[PHASE86 OPERATOR ROI AUDIT] wrote {args.output_dir}")
    return 0 if summary.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

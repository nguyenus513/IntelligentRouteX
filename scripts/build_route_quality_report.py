from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Sequence


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def boolean(value: Any) -> bool:
    return bool(value)


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def load_rows(input_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("dispatch-quality-*-legacy-v2-controlled-*.json")):
        if "compare" in path.name:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        route = payload.get("routeVectorMetrics") if isinstance(payload.get("routeVectorMetrics"), dict) else {}
        objective = payload.get("objectiveTelemetry") if isinstance(payload.get("objectiveTelemetry"), dict) else {}
        selector = payload.get("selectorTelemetry") if isinstance(payload.get("selectorTelemetry"), dict) else {}
        bundle = payload.get("bundleDiversity") if isinstance(payload.get("bundleDiversity"), dict) else {}
        fallback = payload.get("stageFallbackSummary") if isinstance(payload.get("stageFallbackSummary"), dict) else {}

        selected = int(number(metrics.get("selectedProposalCount"), 0))
        executed = int(number(metrics.get("executedAssignmentCount"), 0))
        covered = int(number(metrics.get("coveredOrderCount"), 0))
        utility = number(objective.get("selectedTotalUtility", metrics.get("selectorObjectiveValue", 0.0)))
        risk_cost = number(objective.get("selectedRiskCost", 0.0))
        quality_cost = number(objective.get("selectedQualityCost", 0.0))
        reward = number(objective.get("selectedReward", 0.0))
        route_fallback = number(metrics.get("routeFallbackRate", 0.0))
        worker_fallback = number(metrics.get("workerFallbackRate", 0.0))
        stage_fallbacks = int(number(fallback.get("totalFallbacks", 0), 0))
        geometry_coverage = number(route.get("geometryCoverage", 0.0))
        path_efficiency = number(route.get("averagePathEfficiency", route.get("averageStraightnessScore", 0.0)))
        straightness = number(route.get("averageStraightnessScore", 0.0))
        dominance = number(route.get("routeDominanceRate", 0.0))
        bundle_diversity = int(number(bundle.get("familyDiversityCount", 0), 0))
        pool_cap_loss = number(selector.get("selectorPoolCapObjectiveLoss", 0.0))
        selector_timeout = boolean(selector.get("timedOut", False))

        feasibility_score = 1.0 if boolean(metrics.get("executionValid")) and boolean(metrics.get("conflictFreeAssignments")) else 0.0
        execution_score = clamp(executed / max(1, selected)) if selected else 0.0
        coverage_score = clamp(covered / max(1, selected * 2)) if selected else 0.0
        route_shape_score = mean([clamp(geometry_coverage), clamp(path_efficiency), clamp(straightness), clamp(dominance)])
        fallback_score = clamp(1.0 - max(route_fallback, 1.0 if stage_fallbacks > 0 else 0.0))
        objective_score = clamp((utility + reward - risk_cost - quality_cost) / max(1.0, selected)) if selected else 0.0
        selector_score = 0.0 if selector_timeout or pool_cap_loss > 0.0 else 1.0
        diversity_score = clamp(bundle_diversity / 3.0)

        quality_score = (
            feasibility_score * 0.22
            + execution_score * 0.16
            + coverage_score * 0.12
            + route_shape_score * 0.18
            + fallback_score * 0.12
            + objective_score * 0.12
            + selector_score * 0.05
            + diversity_score * 0.03
        )

        blockers: list[str] = []
        if feasibility_score < 1.0:
            blockers.append("execution-invalid-or-conflicted")
        if selected <= 0 or executed <= 0:
            blockers.append("no-executed-assignment")
        if route_fallback > 0.0 or stage_fallbacks > 0:
            blockers.append("fallback-used")
        if selector_timeout:
            blockers.append("selector-timeout")
        if pool_cap_loss > 0.0:
            blockers.append("selector-pool-cap-objective-loss")
        if geometry_coverage < 0.95:
            blockers.append("geometry-coverage-low")
        if path_efficiency < 0.60:
            blockers.append("path-efficiency-low")

        rows.append({
            "file": path.name,
            "scenarioPack": payload.get("scenarioPack", "unknown"),
            "workloadSize": payload.get("workloadSize", "unknown"),
            "baselineId": payload.get("baselineId", "unknown"),
            "selectedProposalCount": selected,
            "executedAssignmentCount": executed,
            "coveredOrderCount": covered,
            "executionValid": boolean(metrics.get("executionValid")),
            "conflictFreeAssignments": boolean(metrics.get("conflictFreeAssignments")),
            "routeFallbackRate": route_fallback,
            "workerFallbackRate": worker_fallback,
            "stageFallbacks": stage_fallbacks,
            "selectorTimedOut": selector_timeout,
            "selectorPoolCapObjectiveLoss": pool_cap_loss,
            "objectiveUtility": utility,
            "objectiveRiskCost": risk_cost,
            "objectiveQualityCost": quality_cost,
            "objectiveReward": reward,
            "geometryCoverage": geometry_coverage,
            "pathEfficiency": path_efficiency,
            "straightnessScore": straightness,
            "routeDominanceRate": dominance,
            "bundleFamilyDiversityCount": bundle_diversity,
            "qualityScore": round(quality_score, 6),
            "blockers": blockers,
        })
    return rows


def summarize(rows: list[dict[str, Any]], min_quality_score: float, expected_scenarios: list[str]) -> dict[str, Any]:
    scenario_counts = Counter(row["scenarioPack"] for row in rows)
    missing = [scenario for scenario in expected_scenarios if scenario not in scenario_counts]
    blockers = [row for row in rows if row["blockers"] or row["qualityScore"] < min_quality_score]
    blocker_counts: Counter[str] = Counter()
    for row in blockers:
        for blocker in row["blockers"] or ["quality-score-low"]:
            blocker_counts[blocker] += 1
    scenario_scores: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        scenario_scores[row["scenarioPack"]].append(row["qualityScore"])
    scenario_summary = {
        scenario: {
            "count": len(scores),
            "meanQualityScore": round(mean(scores), 6),
            "minQualityScore": round(min(scores), 6),
        }
        for scenario, scores in sorted(scenario_scores.items())
    }
    return {
        "schemaVersion": "route-quality-report/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "rowCount": len(rows),
        "minQualityScoreGate": min_quality_score,
        "meanQualityScore": round(mean([row["qualityScore"] for row in rows]), 6) if rows else 0.0,
        "minQualityScore": round(min([row["qualityScore"] for row in rows]), 6) if rows else 0.0,
        "scenarioCounts": dict(sorted(scenario_counts.items())),
        "scenarioSummary": scenario_summary,
        "missingExpectedScenarios": missing,
        "blockerCounts": dict(sorted(blocker_counts.items())),
        "badRows": blockers,
        "rows": rows,
        "pass": bool(rows) and not blockers and not missing,
        "passWithLimits": bool(rows) and not blockers and bool(missing),
    }


def markdown(report: dict[str, Any]) -> str:
    verdict = "PASS" if report["pass"] else "PASS_WITH_LIMITS" if report["passWithLimits"] else "FAIL"
    lines = [
        "# Route Quality Report",
        "",
        f"- verdict: `{verdict}`",
        f"- rows: `{report['rowCount']}`",
        f"- mean quality score: `{report['meanQualityScore']}`",
        f"- min quality score: `{report['minQualityScore']}`",
        f"- missing expected scenarios: `{report['missingExpectedScenarios']}`",
        f"- blocker counts: `{report['blockerCounts']}`",
        "",
        "## Scenario Summary",
        "",
        "| Scenario | Count | Mean Quality | Min Quality |",
        "|---|---:|---:|---:|",
    ]
    for scenario, summary in report["scenarioSummary"].items():
        lines.append(f"| {scenario} | {summary['count']} | {summary['meanQualityScore']} | {summary['minQualityScore']} |")
    lines.extend(["", "## Rows", "", "| Scenario | Size | Baseline | Quality | Selected/Executed | Coverage | Path Eff. | Dominance | Blockers |", "|---|---|---|---:|---:|---:|---:|---:|---|"])
    for row in report["rows"]:
        lines.append(
            f"| {row['scenarioPack']} | {row['workloadSize']} | {row['baselineId']} | {row['qualityScore']} | "
            f"{row['selectedProposalCount']}/{row['executedAssignmentCount']} | {row['geometryCoverage']} | "
            f"{row['pathEfficiency']} | {row['routeDominanceRate']} | {row['blockers']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build route quality report from dispatch quality benchmark artifacts.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-quality-score", type=float, default=0.70)
    parser.add_argument("--expected-scenario", action="append", default=[])
    args = parser.parse_args(argv)
    rows = load_rows(Path(args.input_dir))
    report = summarize(rows, args.min_quality_score, args.expected_scenario)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "route_quality_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "route_quality_report.md").write_text(markdown(report), encoding="utf-8")
    print(f"[ROUTE QUALITY] wrote {output_dir}")
    return 0 if report["pass"] or report["passWithLimits"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase63_unified_benchmark_suite_v1"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "benchmark" / "final_system_evaluation_report.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def maybe_read_json(path: Path) -> Any | None:
    return read_json(path) if path.exists() else None


def evaluate(input_dir: Path) -> Dict[str, Any]:
    unified = maybe_read_json(input_dir / "aggregate_summary.json") or {}
    challenger = maybe_read_json(input_dir / "challenger_phase56f" / "phase56b_stable_promoted_summary.json") or {}
    vroom = maybe_read_json(input_dir / "vroom_comparator" / "aggregate_summary.json") or {}
    gap = maybe_read_json(input_dir / "vroom_gap_analyzer" / "phase59_vroom_gap_summary.json") or {}
    challenger_rows = challenger.get("results", [])
    vroom_counts = vroom.get("aggregate", {}).get("classificationCounts", {})
    gap_counts = gap.get("classificationCounts", {})
    safety = {
        "challengerHardViolations": sum(int(row.get("hardViolations", 0) or 0) for row in challenger_rows),
        "challengerOverBudgetCount": sum(1 for row in challenger_rows if row.get("wallClockOverBudget") or row.get("stageRuntimeSummary", {}).get("overBudget")),
        "challengerFailCount": sum(1 for row in challenger_rows if row.get("verdict") == "FAIL"),
        "runtimeMs": runtime_summary([row.get("runtimeMs") for row in challenger_rows]),
    }
    robustness = {
        "vroomTimeoutCount": vroom_counts.get("vroom-timeout", gap.get("vroomTimeoutCount", 0)),
        "vroomHardFailCount": vroom_counts.get("vroom-hard-fail", gap.get("vroomHardFailCount", 0)),
        "challengerHardFailCount": safety["challengerFailCount"],
        "challengerOverBudgetCount": safety["challengerOverBudgetCount"],
    }
    final_verdict = final_verdict_from(safety, robustness, gap_counts)
    return {"schemaVersion": "phase65-final-system-evaluation/v1", "unified": unified, "safety": safety, "qualityVsVroom": {"vroomCounts": vroom_counts, "gapCounts": gap_counts, "vehicleGapSummary": gap.get("vehicleGapSummary"), "distanceGapSummary": gap.get("distanceGapSummary")}, "robustness": robustness, "scenarioAnalysis": scenario_analysis(input_dir), "finalVerdict": final_verdict}


def runtime_summary(values: List[Any]) -> Dict[str, Any]:
    numeric = sorted(float(value) for value in values if value is not None)
    if not numeric:
        return {"count": 0, "p50": None, "p95": None, "p99": None, "max": None}
    return {"count": len(numeric), "p50": percentile(numeric, 0.50), "p95": percentile(numeric, 0.95), "p99": percentile(numeric, 0.99), "max": max(numeric)}


def percentile(values: List[float], quantile: float) -> float:
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * quantile))))
    return values[index]


def scenario_analysis(input_dir: Path) -> Dict[str, Any]:
    manifest_path = REPO_ROOT / "benchmarks" / "synthetic_food" / "generated_v1" / "manifest.json"
    if not manifest_path.exists():
        return {"available": False, "scenarios": []}
    manifest = read_json(manifest_path)
    challenger = maybe_read_json(input_dir / "challenger_phase56f" / "phase56b_stable_promoted_summary.json") or {}
    vroom = maybe_read_json(input_dir / "vroom_comparator" / "aggregate_summary.json") or {}
    challenger_rows = {str(row.get("instance", "")).lower(): row for row in challenger.get("results", [])}
    vroom_rows = {str(row.get("instance", "")).lower(): row for row in vroom.get("rows", [])}
    scenarios = []
    for scenario in manifest.get("scenarios", []):
        key = str(scenario.get("scenario", "")).lower()
        challenger_row = challenger_rows.get(key, {})
        vroom_row = vroom_rows.get(key, {})
        scenarios.append(
            {
                "scenario": scenario.get("scenario"),
                "expectedStress": scenario.get("expectedStress", {}),
                "challengerHardViolations": challenger_row.get("hardViolations"),
                "challengerOverBudget": challenger_row.get("wallClockOverBudget") or challenger_row.get("stageRuntimeSummary", {}).get("overBudget"),
                "challengerVehicleCount": challenger_row.get("vehicleCountAfter"),
                "challengerDistance": challenger_row.get("distanceAfter"),
                "challengerRuntimeMs": challenger_row.get("runtimeMs"),
                "vroomClassification": vroom_row.get("classification"),
                "vroomVehicleCount": vroom_row.get("champion", {}).get("vehicleCount"),
                "vroomDistance": vroom_row.get("champion", {}).get("totalDistance"),
            }
        )
    return {"available": True, "scenarioCount": manifest.get("scenarioCount"), "scenarios": scenarios}


def final_verdict_from(safety: Dict[str, Any], robustness: Dict[str, Any], gap_counts: Dict[str, int]) -> Dict[str, Any]:
    production_safe = safety.get("challengerHardViolations", 0) == 0 and safety.get("challengerOverBudgetCount", 0) == 0 and safety.get("challengerFailCount", 0) == 0
    vroom_quality_wins = gap_counts.get("vroom-quality-win-distance", 0) + gap_counts.get("vroom-quality-win-vehicle-count", 0)
    challenger_quality_wins = gap_counts.get("challenger-quality-win-distance", 0) + gap_counts.get("challenger-quality-win-vehicle-count", 0)
    vroom_missing = robustness.get("vroomTimeoutCount", 0) > 0 or robustness.get("vroomHardFailCount", 0) > 0 or gap_counts.get("vroom-unavailable", 0) > 0
    if vroom_quality_wins == 0 and not vroom_missing:
        industry_quality = "yes"
    elif challenger_quality_wins > 0 or gap_counts.get("tie", 0) > 0:
        industry_quality = "partial"
    else:
        industry_quality = "no"
    bottlenecks = []
    if gap_counts.get("vroom-quality-win-distance", 0) > 0:
        bottlenecks.append("distance polish")
    if gap_counts.get("vroom-quality-win-vehicle-count", 0) > 0:
        bottlenecks.append("vehicle count / route-pool fast mode")
    if robustness.get("vroomTimeoutCount", 0) > 0 or robustness.get("vroomHardFailCount", 0) > 0:
        bottlenecks.append("industry comparator robustness interpretation")
    return {"productionSafe": production_safe, "industryQualityCompetitive": industry_quality, "mainBottlenecks": bottlenecks or ["broader certification"]}


def markdown(report: Dict[str, Any]) -> str:
    safety = report["safety"]
    quality = report["qualityVsVroom"]
    robustness = report["robustness"]
    verdict = report["finalVerdict"]
    lines = [
        "# Final System Evaluation Report",
        "",
        "## Safety",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Challenger hard violations | {safety['challengerHardViolations']} |",
        f"| Challenger overBudget count | {safety['challengerOverBudgetCount']} |",
        f"| Challenger FAIL count | {safety['challengerFailCount']} |",
        f"| Runtime p50/p95/p99 ms | {safety['runtimeMs'].get('p50')} / {safety['runtimeMs'].get('p95')} / {safety['runtimeMs'].get('p99')} |",
        "",
        "## Quality Vs VROOM",
        "",
        f"- VROOM comparator counts: `{json.dumps(quality.get('vroomCounts', {}), sort_keys=True)}`",
        f"- Gap counts: `{json.dumps(quality.get('gapCounts', {}), sort_keys=True)}`",
        f"- Vehicle gap summary: `{json.dumps(quality.get('vehicleGapSummary', {}), sort_keys=True)}`",
        f"- Distance gap summary: `{json.dumps(quality.get('distanceGapSummary', {}), sort_keys=True)}`",
        "",
        "## Robustness",
        "",
        f"- VROOM timeout count: {robustness['vroomTimeoutCount']}",
        f"- VROOM hard-fail count: {robustness['vroomHardFailCount']}",
        f"- Challenger hard-fail count: {robustness['challengerHardFailCount']}",
        f"- Challenger overBudget count: {robustness['challengerOverBudgetCount']}",
        "",
        "## Scenario Analysis",
        "",
        f"- Synthetic food scenarios available: {report['scenarioAnalysis'].get('available')}",
        f"- Scenario count: {report['scenarioAnalysis'].get('scenarioCount', 0)}",
        "",
        "| Scenario | VROOM Class | Challenger Vehicles | Challenger Distance | Runtime ms |",
        "|---|---|---:|---:|---:|",
    ]
    for scenario in report["scenarioAnalysis"].get("scenarios", []):
        lines.append(f"| {scenario.get('scenario')} | {scenario.get('vroomClassification')} | {scenario.get('challengerVehicleCount')} | {scenario.get('challengerDistance')} | {scenario.get('challengerRuntimeMs')} |")
    lines.extend([
        "",
        "## Final Verdict",
        "",
        f"- Production-safe: {verdict['productionSafe']}",
        f"- Industry-quality competitive: {verdict['industryQualityCompetitive']}",
        f"- Main bottlenecks: {', '.join(verdict['mainBottlenecks'])}",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build final system evaluation report from Phase 63 artifacts.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = evaluate(Path(args.input_dir))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(report), encoding="utf-8")
    json_output = output.with_suffix(".json")
    json_output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[PHASE65 FINAL SYSTEM EVALUATION] wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

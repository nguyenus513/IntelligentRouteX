from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ELITE_RESULTS = REPO_ROOT / "artifacts" / "benchmark" / "elite-food-dispatch-intelligence" / "elite_results.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "elite-gap-closure"


RAILS: Dict[str, Dict[str, Any]] = {
    "academic-max-quality-v5": {
        "priority": 10,
        "blockers": ["vehicle-count-gap", "max-quality-not-close-to-bks", "strong-baseline-gap"],
        "goal": "Reduce Homberger/Solomon vehicle-count gap with richer route generation and stronger global selection.",
        "commands": [
            "py -3.13 scripts/run_academic_max_quality.py --profile academic-max-quality --instances C1_10_1,R1_10_1,RC1_10_1 --time-limit 30m",
            "py -3.13 scripts/run_elite_food_dispatch_benchmark.py",
        ],
        "gates": [
            "hardViolationCount == 0",
            "R1_10_1 vehicleGap == 0",
            "RC1_10_1 vehicleGap <= 3",
            "usedBksInSolver == false",
            "caseSpecificRuleUsed == false",
        ],
    },
    "traffic-aware-route-quality": {
        "priority": 20,
        "blockers": ["community-traffic-route-limits"],
        "goal": "Reduce bad peak routes on METR-LA/PeMS-BAY without hiding high-regret traffic periods.",
        "commands": [
            "py -3.13 scripts/run_community_traffic_route_benchmark.py --pairs 50",
            "py -3.13 scripts/run_elite_food_dispatch_benchmark.py",
        ],
        "gates": [
            "badTrafficRouteCount == 0 or every bad route has a selected alternative reason",
            "avgPeakVsOffPeakRatio improves versus previous artifact",
            "routeCount >= 50 when data supports it",
        ],
    },
    "shape-aware-route-beauty": {
        "priority": 30,
        "blockers": ["route-beauty-limits"],
        "goal": "Improve route shape on multi-region DIMACS without reducing evidence coverage.",
        "commands": [
            "py -3.13 scripts/run_route_beauty_benchmark.py --regions NY,BAY,COL,FLA --pairs 50 --node-limit 20000",
            "py -3.13 scripts/run_elite_food_dispatch_benchmark.py",
        ],
        "gates": [
            "regionCount >= 4",
            "evaluatedPairs >= 100",
            "avgNetworkDetourRatio <= 1.35",
            "avgStraightnessScore >= 0.80",
        ],
    },
    "ml-ablation-value": {
        "priority": 40,
        "blockers": ["ml-value-not-proven", "ml-worker-readiness-not-audited"],
        "goal": "Connect local ML policy and prove value against no-ML and heuristic baselines.",
        "commands": [
            "py -3.13 scripts/run_ml_intelligence_benchmark.py",
            "py -3.13 scripts/run_elite_food_dispatch_benchmark.py",
        ],
        "gates": [
            "rl4coImportable == true",
            "localMlPolicyAdapterPresent == true",
            "workerReadinessAudited == true",
            "mlValueProven == true or report negative result honestly",
        ],
    },
    "food-driver-sequence-quality": {
        "priority": 50,
        "blockers": ["food-baseline-only", "driver-quality-baseline-only", "anchor-proxy-only", "sequence-quality-proxy-only", "order-to-delivery-baseline-only", "food-quality-target-gap", "driver-quality-target-gap", "anchor-quality-target-gap", "sequence-quality-target-gap", "order-to-delivery-quality-target-gap"],
        "goal": "Replace proxy food-delivery scores with optimizer-vs-baseline quality deltas.",
        "commands": [
            "py -3.13 scripts/run_external_benchmark_certification.py --suite mdrplib",
            "py -3.13 scripts/run_elite_food_dispatch_benchmark.py",
        ],
        "gates": [
            "hard food violations == 0",
            "servedOrderRate >= greedy insertion baseline",
            "p95Delay and p95FoodOnVehicleTime reported",
            "driver fairness/utilization beats or matches baseline",
        ],
    },
    "dynamic-rolling-horizon-quality": {
        "priority": 60,
        "blockers": ["dynamic-baseline-only", "dynamic-optimizer-comparison-missing"],
        "goal": "Upgrade ICAPS/DPDP from structural continuity to optimizer-quality rolling-horizon comparison.",
        "commands": [
            "py -3.13 scripts/run_dynamic_dispatch_quality_benchmark.py",
            "py -3.13 scripts/run_elite_food_dispatch_benchmark.py",
        ],
        "gates": [
            "activeRouteCorruptionCount == 0",
            "vehicleStateContinuityViolation == 0",
            "servedOrderCount >= insertion baseline",
            "totalTardiness <= baseline or stability tradeoff is reported",
        ],
    },
    "stochastic-community-coverage": {
        "priority": 70,
        "blockers": ["svrpbench-not-integrated", "public-stochastic-vrp-data-missing", "svrpbench-data-source-not-configured", "stochastic-data-manifest-missing", "stochastic-public-data-unreadable"],
        "goal": "Add public stochastic/uncertainty routing evidence beyond deterministic VRPTW and DPDP smoke.",
        "commands": [
            "py -3.13 scripts/download_stochastic_benchmark_data.py",
            "py -3.13 scripts/run_stochastic_community_benchmark.py",
            "py -3.13 scripts/run_elite_food_dispatch_benchmark.py",
        ],
        "gates": [
            "public data source documented",
            "parser/checker artifacts exist",
            "missing data is reported as EVIDENCE_GAP, never PASS",
        ],
    },
}


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def blockers_by_layer(scorecard: Dict[str, Any]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for layer in scorecard.get("layers", []):
        for blocker in layer.get("blockers", []):
            mapping[blocker] = str(layer.get("layer", "unknown"))
    return mapping


def build_plan(scorecard: Dict[str, Any]) -> Dict[str, Any]:
    active_blockers = set(scorecard.get("mainBlockers", []))
    layer_by_blocker = blockers_by_layer(scorecard)
    rails: List[Dict[str, Any]] = []
    for name, spec in RAILS.items():
        matched = [blocker for blocker in spec["blockers"] if blocker in active_blockers]
        if not matched:
            continue
        rails.append({
            "rail": name,
            "priority": spec["priority"],
            "matchedBlockers": matched,
            "layers": sorted({layer_by_blocker.get(blocker, "unknown") for blocker in matched}),
            "goal": spec["goal"],
            "commands": spec["commands"],
            "gates": spec["gates"],
        })
    rails.sort(key=lambda item: int(item["priority"]))
    covered = {blocker for rail in rails for blocker in rail["matchedBlockers"]}
    return {
        "schemaVersion": "elite-gap-closure-plan/v1",
        "sourceVerdict": scorecard.get("finalVerdict"),
        "sourceOverallScore": scorecard.get("overallScore"),
        "activeBlockers": sorted(active_blockers),
        "coveredBlockers": sorted(covered),
        "uncoveredBlockers": sorted(active_blockers - covered),
        "nextRail": rails[0]["rail"] if rails else None,
        "rails": rails,
    }


def markdown(plan: Dict[str, Any]) -> str:
    lines = [
        "# Elite Gap Closure Plan",
        "",
        f"SOURCE_VERDICT = {plan['sourceVerdict']}",
        f"SOURCE_OVERALL_SCORE = {float(plan.get('sourceOverallScore', 0.0)):.3f}",
        f"NEXT_RAIL = {plan.get('nextRail')}",
        "",
        "| Priority | Rail | Layers | Blockers |",
        "| ---: | --- | --- | --- |",
    ]
    for rail in plan.get("rails", []):
        lines.append(f"| {rail['priority']} | `{rail['rail']}` | {', '.join(rail['layers'])} | {', '.join(f'`{item}`' for item in rail['matchedBlockers'])} |")
    lines.extend(["", "## Rail Details", ""])
    for rail in plan.get("rails", []):
        lines.extend([f"### {rail['rail']}", "", rail["goal"], "", "Gates:"])
        lines.extend(f"- {gate}" for gate in rail["gates"])
        lines.append("Commands:")
        lines.extend(f"- `{command}`" for command in rail["commands"])
        lines.append("")
    if plan.get("uncoveredBlockers"):
        lines.extend(["## Uncovered Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in plan["uncoveredBlockers"])
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a prioritized gap-closure plan from the Elite scorecard blockers.")
    parser.add_argument("--elite-results", default=str(DEFAULT_ELITE_RESULTS))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    scorecard = read_json(Path(args.elite_results))
    plan = build_plan(scorecard)
    output_root = Path(args.output_root)
    write_json(output_root / "gap_closure_plan.json", plan)
    (output_root / "gap_closure_plan.md").write_text(markdown(plan), encoding="utf-8")
    print(f"[ELITE GAP CLOSURE JSON] {output_root / 'gap_closure_plan.json'}")
    print(f"[ELITE GAP CLOSURE REPORT] {output_root / 'gap_closure_plan.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

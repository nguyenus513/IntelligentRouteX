from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "elite-food-dispatch-intelligence"
DEFAULT_CERTIFICATION_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "certification-suite-external-only-full"
DEFAULT_MAX_QUALITY_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "academic-objective-quality-v4"
DEFAULT_ROUTE_BEAUTY_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "route-beauty-community"
DEFAULT_ROUTE_CONDITION_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "route-condition-community"
DEFAULT_TRAFFIC_ROUTE_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "community-traffic-route"
DEFAULT_WEATHER_ROUTE_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "community-weather-route"
DEFAULT_PYVRP_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "pyvrp-baseline"
DEFAULT_ML_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "ml-intelligence-community"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def verdict_from_score(score: float, blockers: Sequence[str]) -> str:
    if any(blocker.startswith("hard-") for blocker in blockers):
        return "FAIL"
    if any(blocker.endswith("missing") or blocker == "evidence-gap" for blocker in blockers):
        return "EVIDENCE_GAP"
    if score >= 0.92 and not blockers:
        return "ELITE_PASS"
    if score >= 0.82:
        return "PASS"
    return "PASS_WITH_LIMITS"


def score_bundle_quality(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    mdrp_rows = [row for row in rows if row.get("suite") == "grubhub-mdrplib"]
    if not mdrp_rows:
        return layer("bundleQuality", 0.0, ["mdrplib-missing"], {})
    served = sum(float(row.get("servedOrderCount", 0)) for row in mdrp_rows)
    orders = sum(float(row.get("orderCount", 0)) for row in mdrp_rows)
    late_rate = sum(float(row.get("lateOrderRate", 0.0)) for row in mdrp_rows) / max(1, len(mdrp_rows))
    hard = sum(int(row.get("pickupBeforeReadyTimeViolation", 0)) + int(row.get("courierShiftViolation", 0)) + int(row.get("foodOnVehicleHardViolation", 0)) for row in mdrp_rows)
    served_rate = served / max(1.0, orders)
    score = clamp(served_rate * 0.70 + (1.0 - late_rate) * 0.20 + (1.0 if hard == 0 else 0.0) * 0.10)
    blockers = [] if hard == 0 else ["hard-food-violation"]
    if any(row.get("verdict") == "PASS_WITH_LIMITS" for row in mdrp_rows):
        blockers.append("food-baseline-only")
    return layer("bundleQuality", score, blockers, {"servedOrderRate": served_rate, "lateOrderRate": late_rate, "hardViolationCount": hard})


def score_driver_assignment(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    mdrp_rows = [row for row in rows if row.get("suite") == "grubhub-mdrplib"]
    if not mdrp_rows:
        return layer("driverAssignmentQuality", 0.0, ["mdrplib-missing"], {})
    utilization = sum(float(row.get("courierUtilization", 0.0)) for row in mdrp_rows) / max(1, len(mdrp_rows))
    shift_violations = sum(int(row.get("courierShiftViolation", 0)) for row in mdrp_rows)
    score = clamp(utilization * 0.80 + (1.0 if shift_violations == 0 else 0.0) * 0.20)
    blockers = [] if shift_violations == 0 else ["hard-courier-shift-violation"]
    blockers.append("driver-quality-baseline-only")
    return layer("driverAssignmentQuality", score, blockers, {"courierUtilization": utilization, "courierShiftViolation": shift_violations})


def score_anchor_quality(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    mdrp_rows = [row for row in rows if row.get("suite") == "grubhub-mdrplib"]
    if not mdrp_rows:
        return layer("anchorQuality", 0.0, ["mdrplib-missing"], {})
    pickup_violations = sum(int(row.get("pickupBeforeReadyTimeViolation", 0)) for row in mdrp_rows)
    avg_delay = sum(float(row.get("avgDelay", 0.0)) for row in mdrp_rows) / max(1, len(mdrp_rows))
    score = clamp((1.0 if pickup_violations == 0 else 0.0) * 0.70 + max(0.0, 1.0 - avg_delay / 90.0) * 0.30)
    blockers = [] if pickup_violations == 0 else ["hard-pickup-before-ready-violation"]
    blockers.append("anchor-proxy-only")
    return layer("anchorQuality", score, blockers, {"pickupBeforeReadyViolation": pickup_violations, "avgDelay": avg_delay})


def score_sequence_quality(rows: Sequence[Dict[str, Any]], layer_name: str) -> Dict[str, Any]:
    sequence_rows = [row for row in rows if row.get("suite") in {"li-lim", "grubhub-mdrplib"}]
    if not sequence_rows:
        return layer(layer_name, 0.0, ["sequence-data-missing"], {})
    pickup_violations = sum(int(row.get("pickupBeforeDropoffViolationCount", 0)) for row in sequence_rows)
    time_violations = sum(int(row.get("timeWindowViolationCount", 0)) for row in sequence_rows)
    late_rate_values = [float(row.get("lateOrderRate", 0.0)) for row in sequence_rows if "lateOrderRate" in row]
    late_rate = sum(late_rate_values) / max(1, len(late_rate_values))
    score = clamp((1.0 if pickup_violations == 0 else 0.0) * 0.45 + (1.0 if time_violations == 0 else 0.0) * 0.35 + (1.0 - late_rate) * 0.20)
    blockers = []
    if pickup_violations:
        blockers.append("hard-pickup-dropoff-violation")
    if time_violations:
        blockers.append("hard-time-window-violation")
    blockers.append("sequence-quality-proxy-only")
    return layer(layer_name, score, blockers, {"pickupBeforeDropoffViolation": pickup_violations, "timeWindowViolation": time_violations, "lateOrderRate": late_rate})


def score_road_beauty(route_beauty_root: Path) -> Dict[str, Any]:
    path = route_beauty_root / "route_beauty_results.json"
    if not path.exists():
        return layer("roadRouteBeauty", 0.0, ["route-beauty-missing"], {})
    result = read_json(path)
    if result.get("finalVerdict") == "FAIL":
        blockers = ["hard-road-route-failure"]
    elif result.get("finalVerdict") == "EVIDENCE_GAP":
        blockers = ["evidence-gap"]
    else:
        blockers = [] if result.get("finalVerdict") == "PASS" else ["route-beauty-limits"]
    straightness = float(result.get("avgStraightnessScore", 0.0))
    detour = float(result.get("avgNetworkDetourRatio", 10.0))
    score = clamp(straightness * 0.55 + max(0.0, 1.0 - max(0.0, detour - 1.0) / 3.0) * 0.45)
    return layer("roadRouteBeauty", score, blockers, {"avgStraightnessScore": straightness, "avgNetworkDetourRatio": detour, "evaluatedPairs": result.get("evaluatedPairs", 0)})


def score_order_to_delivery(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    mdrp_rows = [row for row in rows if row.get("suite") == "grubhub-mdrplib"]
    if not mdrp_rows:
        return layer("orderToDeliveryQuality", 0.0, ["mdrplib-missing"], {})
    avg_delay = sum(float(row.get("avgDelay", 0.0)) for row in mdrp_rows) / max(1, len(mdrp_rows))
    avg_food = sum(float(row.get("avgFoodOnVehicleTime", 0.0)) for row in mdrp_rows) / max(1, len(mdrp_rows))
    late_rate = sum(float(row.get("lateOrderRate", 0.0)) for row in mdrp_rows) / max(1, len(mdrp_rows))
    score = clamp(max(0.0, 1.0 - avg_delay / 90.0) * 0.45 + max(0.0, 1.0 - avg_food / 45.0) * 0.35 + (1.0 - late_rate) * 0.20)
    return layer("orderToDeliveryQuality", score, ["order-to-delivery-baseline-only"], {"avgDelay": avg_delay, "avgFoodOnVehicleTime": avg_food, "lateOrderRate": late_rate})


def score_dynamic_dispatch(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    dynamic_rows = [row for row in rows if row.get("suite") in {"icaps-dpdp", "dpdp-stress"}]
    if not dynamic_rows:
        return layer("dynamicDispatchQuality", 0.0, ["dynamic-data-missing"], {})
    hard = sum(int(row.get("activeRouteCorruptionCount", 0)) + int(row.get("vehicleStateContinuityViolation", 0)) for row in dynamic_rows)
    pass_rate = sum(1 for row in dynamic_rows if row.get("verdict") in {"PASS", "PASS_WITH_LIMITS"}) / max(1, len(dynamic_rows))
    score = clamp(pass_rate * 0.70 + (1.0 if hard == 0 else 0.0) * 0.30)
    blockers = [] if hard == 0 else ["hard-dynamic-continuity-violation"]
    if any(row.get("suite") == "icaps-dpdp" and row.get("verdict") == "PASS_WITH_LIMITS" for row in dynamic_rows):
        blockers.append("dynamic-baseline-only")
    return layer("dynamicDispatchQuality", score, blockers, {"hardViolationCount": hard, "rowCount": len(dynamic_rows)})


def score_ml_intelligence(ml_root: Path) -> Dict[str, Any]:
    path = ml_root / "ml_intelligence_results.json"
    if not path.exists():
        return layer("mlIntelligence", 0.0, ["ml-community-benchmark-missing", "rl4co-not-integrated"], {"mlValueProven": False})
    result = read_json(path)
    if result.get("finalVerdict") == "EVIDENCE_GAP":
        return layer("mlIntelligence", 0.0, result.get("verdictReasons", ["ml-community-benchmark-missing"]), {"mlValueProven": False, "rl4coAvailable": result.get("rl4coAvailable")})
    score = 0.5 if result.get("rl4coAvailable") else 0.0
    if result.get("mlValueProven"):
        score = 1.0
    blockers = [] if result.get("mlValueProven") else ["ml-value-not-proven"]
    return layer("mlIntelligence", score, blockers, result)


def score_baseline_competitiveness(rows: Sequence[Dict[str, Any]], max_quality_root: Path, pyvrp_root: Path) -> Dict[str, Any]:
    academic_rows = [row for row in rows if row.get("stage") in {"A-academic-correctness", "B-scale"}]
    max_quality_path = max_quality_root / "academic_max_quality_results.json"
    max_quality_rows = read_json(max_quality_path).get("results", []) if max_quality_path.exists() else []
    rows_with_bks = [row for row in academic_rows if row.get("bestKnownVehicleCount") is not None or row.get("bestKnownDistance") is not None]
    pass_rows = [row for row in academic_rows if row.get("verdict") == "PASS"]
    close_max_quality = [row for row in max_quality_rows if int(row.get("vehicleGap", 999)) <= 1]
    bks_coverage = len(rows_with_bks) / max(1, len(academic_rows))
    pass_rate = len(pass_rows) / max(1, len(academic_rows))
    close_rate = len(close_max_quality) / max(1, len(max_quality_rows))
    pyvrp_path = pyvrp_root / "pyvrp_results.json"
    pyvrp_score = 0.0
    pyvrp_blocker = "pyvrp-hgs-baseline-not-integrated"
    if pyvrp_path.exists():
        pyvrp = read_json(pyvrp_path)
        pyvrp_rows = pyvrp.get("results", [])
        if pyvrp.get("pyvrpInstalled") and pyvrp_rows and all(row.get("verdict") != "EVIDENCE_GAP" for row in pyvrp_rows):
            pyvrp_score = 1.0
            pyvrp_blocker = ""
        else:
            pyvrp_blocker = "pyvrp-hgs-baseline-evidence-gap"
    score = clamp(bks_coverage * 0.20 + pass_rate * 0.30 + close_rate * 0.30 + pyvrp_score * 0.20)
    blockers = []
    if pass_rate < 0.75:
        blockers.append("strong-baseline-gap")
    if close_rate < 0.75:
        blockers.append("max-quality-not-close-to-bks")
    if pyvrp_blocker:
        blockers.append(pyvrp_blocker)
    return layer("baselineCompetitiveness", score, blockers, {"bksCoverage": bks_coverage, "academicPassRate": pass_rate, "maxQualityCloseRate": close_rate, "pyvrpBaselineScore": pyvrp_score})


def score_evidence_depth(rows: Sequence[Dict[str, Any]], route_beauty_root: Path) -> Dict[str, Any]:
    suite_names = {str(row.get("suite")) for row in rows}
    expected = {"solomon", "li-lim", "homberger-vrptw", "grubhub-mdrplib", "icaps-dpdp", "dpdp-stress"}
    route_beauty = route_beauty_root / "route_beauty_results.json"
    covered = len(expected & suite_names) + (1 if route_beauty.exists() else 0)
    total = len(expected) + 1
    score = covered / total
    blockers = []
    if "grubhub-mdrplib" not in suite_names:
        blockers.append("mdrplib-missing")
    if "icaps-dpdp" not in suite_names:
        blockers.append("icaps-missing")
    if not route_beauty.exists():
        blockers.append("route-beauty-missing")
    blockers.append("svrpbench-not-integrated")
    return layer("evidenceDepth", score, blockers, {"coveredBenchmarkFamilies": covered, "expectedBenchmarkFamilies": total, "suiteNames": sorted(suite_names)})


def score_route_beauty_readiness(route_beauty_root: Path) -> Dict[str, Any]:
    path = route_beauty_root / "route_beauty_results.json"
    if not path.exists():
        return layer("routeBeautyReadiness", 0.0, ["route-beauty-missing"], {})
    result = read_json(path)
    evaluated = int(result.get("evaluatedPairs", 0))
    region_count = int(result.get("regionCount", 1))
    single_region_score = clamp(region_count / 4.0)
    pair_score = clamp(evaluated / 50.0)
    score = clamp(single_region_score + pair_score * 0.5)
    blockers = []
    if evaluated < 50:
        blockers.append("route-beauty-pair-count-low")
    if region_count < 4:
        blockers.append("route-beauty-single-region-only")
    return layer("routeBeautyReadiness", score, blockers, {"evaluatedPairs": evaluated, "regionCount": region_count, "regions": result.get("regions", [result.get("benchmarkFamily", "unknown")])})


def score_driver_route_condition(route_condition_root: Path) -> Dict[str, Any]:
    path = route_condition_root / "route_condition_results.json"
    if not path.exists():
        return layer("driverRouteConditionQuality", 0.0, ["route-condition-benchmark-missing"], {})
    result = read_json(path)
    if result.get("finalVerdict") == "EVIDENCE_GAP":
        return layer("driverRouteConditionQuality", 0.0, result.get("verdictReasons", ["route-condition-evidence-gap"]), result)
    bad = int(result.get("badConditionRouteCount", 0))
    total = int(result.get("evaluatedRoutes", 0)) or 1
    distance_ratio = float(result.get("avgDistanceRatio", 2.0))
    cost_ratio = float(result.get("avgConditionCostRatio", 3.0))
    straightness = float(result.get("avgStraightnessScore", 0.0))
    score = clamp((1.0 - bad / total) * 0.35 + max(0.0, 1.0 - max(0.0, distance_ratio - 1.0) / 0.5) * 0.25 + max(0.0, 1.0 - max(0.0, cost_ratio - 1.0) / 1.5) * 0.20 + straightness * 0.20)
    blockers = [] if bad == 0 else ["driver-route-condition-limits"]
    return layer("driverRouteConditionQuality", score, blockers, {"evaluatedRoutes": total, "badConditionRouteCount": bad, "avgDistanceRatio": distance_ratio, "avgConditionCostRatio": cost_ratio, "avgStraightnessScore": straightness})


def score_community_traffic_route(traffic_route_root: Path) -> Dict[str, Any]:
    path = traffic_route_root / "traffic_route_results.json"
    if not path.exists():
        return layer("communityTrafficRouteQuality", 0.0, ["community-traffic-route-missing"], {})
    result = read_json(path)
    if result.get("finalVerdict") == "EVIDENCE_GAP":
        return layer("communityTrafficRouteQuality", 0.0, ["community-traffic-data-missing"], result)
    datasets = result.get("datasets", [])
    routes = sum(int(row.get("routeCount", 0)) for row in datasets)
    bad = sum(int(row.get("badTrafficRouteCount", 0)) for row in datasets)
    avg_ratio_values = [float(row.get("avgPeakVsOffPeakRatio", 1.0)) for row in datasets if row.get("routeCount", 0)]
    avg_ratio = sum(avg_ratio_values) / max(1, len(avg_ratio_values))
    score = clamp((1.0 - bad / max(1, routes)) * 0.55 + max(0.0, 1.0 - max(0.0, avg_ratio - 1.0) / 1.5) * 0.45)
    blockers = [] if result.get("finalVerdict") == "PASS" else ["community-traffic-route-limits"]
    return layer("communityTrafficRouteQuality", score, blockers, {"routeCount": routes, "badTrafficRouteCount": bad, "avgPeakVsOffPeakRatio": avg_ratio})


def score_community_weather_route(weather_route_root: Path) -> Dict[str, Any]:
    path = weather_route_root / "weather_route_results.json"
    if not path.exists():
        return layer("communityWeatherRouteQuality", 0.0, ["community-weather-route-missing"], {})
    result = read_json(path)
    if result.get("finalVerdict") == "EVIDENCE_GAP":
        reasons = []
        for dataset in result.get("datasets", []):
            reasons.extend(dataset.get("verdictReasons", []))
        return layer("communityWeatherRouteQuality", 0.0, reasons or ["community-weather-data-missing"], result)
    datasets = result.get("datasets", [])
    routes = sum(int(row.get("routeCount", 0)) for row in datasets)
    bad = sum(int(row.get("badWeatherRouteCount", 0)) for row in datasets)
    avg_cost_values = [float(row.get("avgWeatherCostRatio", 1.0)) for row in datasets if row.get("routeCount", 0)]
    avg_distance_values = [float(row.get("avgDistanceRatio", 1.0)) for row in datasets if row.get("routeCount", 0)]
    straightness_values = [float(row.get("avgStraightnessScore", 0.0)) for row in datasets if row.get("routeCount", 0)]
    avg_cost = sum(avg_cost_values) / max(1, len(avg_cost_values))
    avg_distance = sum(avg_distance_values) / max(1, len(avg_distance_values))
    straightness = sum(straightness_values) / max(1, len(straightness_values))
    score = clamp((1.0 - bad / max(1, routes)) * 0.40 + max(0.0, 1.0 - max(0.0, avg_cost - 1.0) / 1.5) * 0.25 + max(0.0, 1.0 - max(0.0, avg_distance - 1.0) / 0.5) * 0.20 + straightness * 0.15)
    blockers = [] if result.get("finalVerdict") == "PASS" else ["community-weather-route-limits"]
    return layer("communityWeatherRouteQuality", score, blockers, {"routeCount": routes, "badWeatherRouteCount": bad, "avgWeatherCostRatio": avg_cost, "avgDistanceRatio": avg_distance, "avgStraightnessScore": straightness})


def score_runtime_quality(rows: Sequence[Dict[str, Any]], max_quality_root: Path) -> Dict[str, Any]:
    runtimes = [float(row.get("runtimeMs", 0.0)) for row in rows if "runtimeMs" in row]
    avg_runtime = sum(runtimes) / max(1, len(runtimes))
    max_quality_path = max_quality_root / "academic_max_quality_results.json"
    max_quality_minutes = 0.0
    if max_quality_path.exists():
        max_quality = read_json(max_quality_path)
        max_quality_minutes = sum(float(row.get("runtimeMinutes", 0.0)) for row in max_quality.get("results", []))
    score = clamp(max(0.0, 1.0 - avg_runtime / 180_000.0) * 0.60 + max(0.0, 1.0 - max_quality_minutes / 120.0) * 0.40)
    blockers = [] if avg_runtime <= 180_000 else ["runtime-high"]
    return layer("runtimeQuality", score, blockers, {"avgExternalRuntimeMs": avg_runtime, "maxQualityRuntimeMinutesTotal": max_quality_minutes})


def score_system_reliability(certification: Dict[str, Any]) -> Dict[str, Any]:
    counts = certification.get("verdictCounts", {})
    total = sum(int(value) for value in counts.values()) or 1
    fail = int(counts.get("FAIL", 0))
    gap = int(counts.get("EVIDENCE_GAP", 0))
    score = clamp(1.0 - (fail + gap) / total)
    blockers = []
    if fail:
        blockers.append("hard-fail-row")
    if gap:
        blockers.append("evidence-gap")
    return layer("systemReliability", score, blockers, counts)


ACTION_BY_BLOCKER = {
    "vehicle-count-gap": "Add stronger ALNS/ejection-chain route generation and rerun Homberger R/RC max-quality.",
    "ml-community-benchmark-missing": "Integrate RL4CO or an equivalent public ML routing benchmark with no-ML ablation.",
    "rl4co-not-integrated": "Add RL4CO adapter and report ML gap versus heuristic/PyVRP baselines.",
    "rl4co-package-not-installed": "Install RL4CO in the benchmark environment or add a containerized RL4CO runner.",
    "our-ml-policy-adapter-missing": "Expose local ML policy inference for no-ML versus ML benchmark comparison.",
    "pyvrp-hgs-baseline-not-integrated": "Run PyVRP/HGS baselines for Solomon/Homberger and compare vehicle/distance gaps.",
    "pyvrp-hgs-baseline-evidence-gap": "Install PyVRP and complete the Solomon/Homberger adapter for HGS comparison.",
    "svrpbench-not-integrated": "Add SVRPBench stochastic VRP cases for robustness under delay/traffic uncertainty.",
    "food-baseline-only": "Upgrade MDRPLib from structural baseline to optimizer quality with bundle/delay/utilization comparisons.",
    "driver-quality-baseline-only": "Add driver fairness, utilization distribution, and baseline comparison on MDRPLib.",
    "dynamic-baseline-only": "Upgrade ICAPS from structural rolling-horizon checks to optimizer-vs-baseline dynamic quality.",
    "route-beauty-single-region-only": "Add DIMACS BAY/COL/FLA or OSRM OSM extracts for multi-region route-beauty evidence.",
    "route-beauty-pair-count-low": "Increase route-beauty pair count to at least 50 per region.",
    "route-condition-benchmark-missing": "Run route-condition benchmark with clear/rain/traffic/storm profiles.",
    "driver-route-condition-limits": "Tune route selection to reduce traffic/weather cost, distance ratio, and driver turn burden.",
    "community-traffic-route-missing": "Run METR-LA/PeMS-BAY community traffic route benchmark.",
    "community-traffic-data-missing": "Download or place METR-LA/PeMS-BAY official community traffic files.",
    "community-traffic-route-limits": "Improve traffic-aware route selection against sensor peak/off-peak benchmark.",
    "community-weather-route-missing": "Run Open-Meteo plus DIMACS community weather route benchmark.",
    "community-weather-data-missing": "Download public Open-Meteo historical weather data for route stress evaluation.",
    "community-weather-route-limits": "Improve weather-aware route selection, keeping route shape and detour under bad-weather stress.",
    "no-weather-stress-events": "Use a public historical weather window with rain or wind stress events.",
}


def build_action_plan(blockers: Sequence[str]) -> List[Dict[str, str]]:
    priority = [
        "ml-community-benchmark-missing",
        "rl4co-not-integrated",
        "pyvrp-hgs-baseline-not-integrated",
        "vehicle-count-gap",
        "food-baseline-only",
        "dynamic-baseline-only",
        "svrpbench-not-integrated",
        "route-beauty-single-region-only",
        "route-beauty-pair-count-low",
        "community-weather-route-missing",
        "community-weather-data-missing",
    ]
    ordered = [blocker for blocker in priority if blocker in blockers] + [blocker for blocker in blockers if blocker not in priority]
    return [{"blocker": blocker, "recommendedAction": ACTION_BY_BLOCKER.get(blocker, "Investigate and add a targeted benchmark or baseline.")} for blocker in ordered]


def score_academic(max_quality_root: Path, rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    max_quality_path = max_quality_root / "academic_max_quality_results.json"
    if max_quality_path.exists():
        result = read_json(max_quality_path)
        cases = result.get("results", [])
        hard = sum(int(row.get("hardViolationCount", 0)) for row in cases)
        vehicle_gap = sum(max(0, int(row.get("vehicleGap", 0))) for row in cases)
        score = clamp((1.0 if hard == 0 else 0.0) * 0.50 + max(0.0, 1.0 - vehicle_gap / 12.0) * 0.50)
        blockers = [] if hard == 0 else ["hard-academic-violation"]
        if vehicle_gap:
            blockers.append("vehicle-count-gap")
        return layer("academicRoutingQuality", score, blockers, {"vehicleGapTotal": vehicle_gap, "hardViolationCount": hard})
    academic_rows = [row for row in rows if row.get("stage") in {"A-academic-correctness", "B-scale"}]
    pass_rate = sum(1 for row in academic_rows if row.get("verdict") == "PASS") / max(1, len(academic_rows))
    return layer("academicRoutingQuality", pass_rate, ["max-quality-missing"], {"rowCount": len(academic_rows)})


def layer(name: str, score: float, blockers: Sequence[str], metrics: Dict[str, Any]) -> Dict[str, Any]:
    blockers = sorted(set(blockers))
    return {
        "layer": name,
        "score": score,
        "verdict": verdict_from_score(score, blockers),
        "blockers": blockers,
        "metrics": metrics,
    }


def final_verdict(layers: Sequence[Dict[str, Any]]) -> str:
    if any(layer["verdict"] == "FAIL" for layer in layers):
        return "FAIL"
    if any(layer["verdict"] == "EVIDENCE_GAP" for layer in layers):
        return "PASS_WITH_LIMITS"
    if all(layer["verdict"] == "ELITE_PASS" for layer in layers):
        return "ELITE_PASS"
    if all(layer["verdict"] in {"ELITE_PASS", "PASS"} for layer in layers):
        return "PASS"
    return "PASS_WITH_LIMITS"


def build_elite_scorecard(certification_root: Path, max_quality_root: Path, route_beauty_root: Path, pyvrp_root: Path = DEFAULT_PYVRP_ROOT, ml_root: Path = DEFAULT_ML_ROOT, route_condition_root: Path = DEFAULT_ROUTE_CONDITION_ROOT, traffic_route_root: Path = DEFAULT_TRAFFIC_ROUTE_ROOT, weather_route_root: Path = DEFAULT_WEATHER_ROUTE_ROOT) -> Dict[str, Any]:
    certification_path = certification_root / "certification_suite_results.json"
    if not certification_path.exists():
        layers = [layer("systemReliability", 0.0, ["certification-suite-missing"], {})]
        return {"schemaVersion": "elite-food-dispatch-intelligence/v1", "finalVerdict": "EVIDENCE_GAP", "overallScore": 0.0, "layers": layers}
    certification = read_json(certification_path)
    rows = certification.get("results", [])
    layers = [
        score_academic(max_quality_root, rows),
        score_bundle_quality(rows),
        score_driver_assignment(rows),
        score_anchor_quality(rows),
        score_sequence_quality(rows, "pickupSequenceQuality"),
        score_sequence_quality(rows, "dropoffSequenceQuality"),
        score_road_beauty(route_beauty_root),
        score_driver_route_condition(route_condition_root),
        score_community_traffic_route(traffic_route_root),
        score_community_weather_route(weather_route_root),
        score_order_to_delivery(rows),
        score_dynamic_dispatch(rows),
        score_ml_intelligence(ml_root),
        score_baseline_competitiveness(rows, max_quality_root, pyvrp_root),
        score_evidence_depth(rows, route_beauty_root),
        score_route_beauty_readiness(route_beauty_root),
        score_runtime_quality(rows, max_quality_root),
        score_system_reliability(certification),
    ]
    overall = sum(float(item["score"]) for item in layers) / max(1, len(layers))
    blockers = sorted({blocker for item in layers for blocker in item.get("blockers", [])})
    return {
        "schemaVersion": "elite-food-dispatch-intelligence/v1",
        "sourceCertification": str(certification_path),
        "sourceMaxQuality": str(max_quality_root / "academic_max_quality_results.json"),
        "sourceRouteBeauty": str(route_beauty_root / "route_beauty_results.json"),
        "sourceRouteCondition": str(route_condition_root / "route_condition_results.json"),
        "sourceTrafficRoute": str(traffic_route_root / "traffic_route_results.json"),
        "sourceWeatherRoute": str(weather_route_root / "weather_route_results.json"),
        "sourcePyvrp": str(pyvrp_root / "pyvrp_results.json"),
        "sourceMlIntelligence": str(ml_root / "ml_intelligence_results.json"),
        "finalVerdict": final_verdict(layers),
        "overallScore": overall,
        "mainBlockers": blockers,
        "actionPlan": build_action_plan(blockers),
        "layers": layers,
    }


def markdown(scorecard: Dict[str, Any]) -> str:
    lines = [
        "# Elite Food Dispatch Intelligence Benchmark",
        "",
        f"FINAL_VERDICT = {scorecard['finalVerdict']}",
        f"OVERALL_SCORE = {scorecard['overallScore']:.3f}",
        "",
        "| Layer | Score | Verdict | Blockers |",
        "| --- | ---: | --- | --- |",
    ]
    for item in scorecard.get("layers", []):
        blockers = ", ".join(item.get("blockers", [])) or "none"
        lines.append(f"| `{item['layer']}` | `{item['score']:.3f}` | `{item['verdict']}` | `{blockers}` |")
    lines.extend(["", "## Main Blockers", ""])
    for blocker in scorecard.get("mainBlockers", []):
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Action Plan", ""])
    for item in scorecard.get("actionPlan", []):
        lines.append(f"- `{item['blocker']}`: {item['recommendedAction']}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Elite Food Dispatch Intelligence meta-benchmark scorecard.")
    parser.add_argument("--certification-root", default=str(DEFAULT_CERTIFICATION_ROOT))
    parser.add_argument("--max-quality-root", default=str(DEFAULT_MAX_QUALITY_ROOT))
    parser.add_argument("--route-beauty-root", default=str(DEFAULT_ROUTE_BEAUTY_ROOT))
    parser.add_argument("--route-condition-root", default=str(DEFAULT_ROUTE_CONDITION_ROOT))
    parser.add_argument("--traffic-route-root", default=str(DEFAULT_TRAFFIC_ROUTE_ROOT))
    parser.add_argument("--weather-route-root", default=str(DEFAULT_WEATHER_ROUTE_ROOT))
    parser.add_argument("--pyvrp-root", default=str(DEFAULT_PYVRP_ROOT))
    parser.add_argument("--ml-root", default=str(DEFAULT_ML_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    scorecard = build_elite_scorecard(Path(args.certification_root), Path(args.max_quality_root), Path(args.route_beauty_root), Path(args.pyvrp_root), Path(args.ml_root), Path(args.route_condition_root), Path(args.traffic_route_root), Path(args.weather_route_root))
    write_json(output_root / "elite_results.json", scorecard)
    (output_root / "elite_report.md").write_text(markdown(scorecard), encoding="utf-8")
    write_json(output_root / "scorecard.json", scorecard)
    (output_root / "scorecard.md").write_text(markdown(scorecard), encoding="utf-8")
    print(f"[ELITE BENCHMARK JSON] {output_root / 'elite_results.json'}")
    print(f"[ELITE BENCHMARK REPORT] {output_root / 'elite_report.md'}")
    return 1 if scorecard["finalVerdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CERTIFICATION_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "certification-suite-external-only-full"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "food-dispatch-quality"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def average(rows: Sequence[Dict[str, Any]], key: str, default: float = 0.0) -> float:
    values = [float(row.get(key, default)) for row in rows if row.get(key) is not None]
    return sum(values) / max(1, len(values))


def maximum(rows: Sequence[Dict[str, Any]], key: str, default: float = 0.0) -> float:
    values = [float(row.get(key, default)) for row in rows if row.get(key) is not None]
    return max(values, default=default)


def top_instances(rows: Sequence[Dict[str, Any]], key: str, limit: int = 5) -> List[Dict[str, Any]]:
    ranked = sorted(
        (row for row in rows if row.get(key) is not None),
        key=lambda row: float(row.get(key, 0.0)),
        reverse=True,
    )
    return [{"instance": row.get("instanceName") or row.get("instance"), key: row.get(key)} for row in ranked[:limit]]


def recommendations(layers: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    mapping = {
        "food-quality-target-gap": "Reduce p95 delay and p95 food-on-vehicle time with freshness-aware batching and ready-time-aware insertion.",
        "driver-quality-target-gap": "Improve courier fairness and utilization with min-cost assignment or fairness-aware penalties.",
        "anchor-quality-target-gap": "Reduce pickup wait and p95 order-to-delivery by choosing anchors closer to ready restaurants and active courier corridors.",
        "order-to-delivery-quality-target-gap": "Optimize end-to-end delivery p95 using delay-aware sequence repair and max-delay penalties.",
    }
    blockers = sorted({blocker for layer_item in layers for blocker in layer_item.get("blockers", [])})
    return [{"blocker": blocker, "recommendedOptimizationTarget": mapping.get(blocker, "Investigate the worst instances and add a targeted quality objective.")} for blocker in blockers]


def layer(name: str, score: float, verdict: str, blockers: Sequence[str], metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {"layer": name, "score": max(0.0, min(1.0, score)), "verdict": verdict, "blockers": sorted(set(blockers)), "metrics": metrics}


def verdict(score: float, blockers: Sequence[str]) -> str:
    if any(blocker.startswith("hard-") for blocker in blockers):
        return "FAIL"
    if score >= 0.90 and not blockers:
        return "PASS"
    return "PASS_WITH_LIMITS"


def score_food(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    served_rate = sum(float(row.get("servedOrderCount", 0)) for row in rows) / max(1.0, sum(float(row.get("orderCount", 0)) for row in rows))
    late_rate = average(rows, "lateOrderRate")
    p95_delay = maximum(rows, "p95Delay")
    p95_food = maximum(rows, "p95FoodOnVehicleTime")
    hard = sum(int(row.get("pickupBeforeReadyTimeViolation", 0)) + int(row.get("courierShiftViolation", 0)) + int(row.get("foodOnVehicleHardViolation", 0)) for row in rows)
    score = served_rate * 0.35 + (1.0 - late_rate) * 0.25 + max(0.0, 1.0 - p95_delay / 45.0) * 0.20 + max(0.0, 1.0 - p95_food / 30.0) * 0.20
    blockers: List[str] = []
    if hard:
        blockers.append("hard-food-violation")
    if p95_delay > 45.0:
        blockers.append("p95-delay-above-target")
    if p95_food > 30.0:
        blockers.append("p95-food-on-vehicle-above-target")
    if score < 0.90 and not blockers:
        blockers.append("food-quality-target-gap")
    return layer("bundleQuality", score, verdict(score, blockers), blockers, {"servedOrderRate": served_rate, "lateOrderRate": late_rate, "p95DelayMax": p95_delay, "p95FoodOnVehicleTimeMax": p95_food, "hardViolationCount": hard})


def score_driver(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    utilization = average(rows, "courierUtilization")
    gini = average(rows, "assignmentFairnessGini")
    p95_orders = maximum(rows, "ordersPerCourierP95")
    shift = sum(int(row.get("courierShiftViolation", 0)) for row in rows)
    score = utilization * 0.45 + max(0.0, 1.0 - gini) * 0.35 + max(0.0, 1.0 - max(0.0, p95_orders - 15.0) / 20.0) * 0.20
    blockers: List[str] = []
    if shift:
        blockers.append("hard-courier-shift-violation")
    if gini > 0.65:
        blockers.append("driver-fairness-gini-high")
    if score < 0.90 and not blockers:
        blockers.append("driver-quality-target-gap")
    return layer("driverAssignmentQuality", score, verdict(score, blockers), blockers, {"courierUtilization": utilization, "assignmentFairnessGini": gini, "ordersPerCourierP95Max": p95_orders, "courierShiftViolation": shift})


def score_anchor(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    pickup_wait = average(rows, "avgPickupWaitTime")
    pickup_violations = sum(int(row.get("pickupBeforeReadyTimeViolation", 0)) for row in rows)
    p95_order_to_delivery = maximum(rows, "p95OrderToDeliveryTime")
    score = (1.0 if pickup_violations == 0 else 0.0) * 0.45 + max(0.0, 1.0 - pickup_wait / 10.0) * 0.30 + max(0.0, 1.0 - p95_order_to_delivery / 75.0) * 0.25
    blockers = ["hard-pickup-before-ready-violation"] if pickup_violations else []
    if score < 0.90 and not blockers:
        blockers.append("anchor-quality-target-gap")
    return layer("anchorQuality", score, verdict(score, blockers), blockers, {"avgPickupWaitTime": pickup_wait, "pickupBeforeReadyViolation": pickup_violations, "p95OrderToDeliveryTimeMax": p95_order_to_delivery})


def score_sequence(rows: Sequence[Dict[str, Any]], name: str) -> Dict[str, Any]:
    pickup_dropoff = sum(int(row.get("pickupBeforeDropoffViolationCount", 0)) for row in rows)
    late_rate = average(rows, "lateOrderRate")
    p95_food = maximum(rows, "p95FoodOnVehicleTime")
    score = (1.0 if pickup_dropoff == 0 else 0.0) * 0.45 + (1.0 - late_rate) * 0.30 + max(0.0, 1.0 - p95_food / 30.0) * 0.25
    blockers = ["hard-pickup-dropoff-violation"] if pickup_dropoff else []
    if score < 0.90 and not blockers:
        blockers.append("sequence-quality-target-gap")
    return layer(name, score, verdict(score, blockers), blockers, {"pickupBeforeDropoffViolation": pickup_dropoff, "lateOrderRate": late_rate, "p95FoodOnVehicleTimeMax": p95_food})


def score_order_to_delivery(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    p95_otd = maximum(rows, "p95OrderToDeliveryTime")
    avg_otd = average(rows, "avgOrderToDeliveryTime")
    p95_delay = maximum(rows, "p95Delay")
    score = max(0.0, 1.0 - p95_otd / 75.0) * 0.45 + max(0.0, 1.0 - avg_otd / 50.0) * 0.30 + max(0.0, 1.0 - p95_delay / 45.0) * 0.25
    blockers: List[str] = []
    if p95_otd > 75.0:
        blockers.append("p95-order-to-delivery-above-target")
    if score < 0.90 and not blockers:
        blockers.append("order-to-delivery-quality-target-gap")
    return layer("orderToDeliveryQuality", score, verdict(score, blockers), blockers, {"p95OrderToDeliveryTimeMax": p95_otd, "avgOrderToDeliveryTime": avg_otd, "p95DelayMax": p95_delay})


def build_quality(certification_root: Path) -> Dict[str, Any]:
    certification_path = certification_root / "certification_suite_results.json"
    if not certification_path.exists():
        return {"schemaVersion": "food-dispatch-quality/v1", "finalVerdict": "EVIDENCE_GAP", "verdictReasons": ["certification-suite-missing"], "layers": []}
    certification = read_json(certification_path)
    metrics_by_instance = {}
    for metrics_path in (certification_root / "mdrplib").glob("*/metrics.json"):
        metrics = read_json(metrics_path)
        metrics_by_instance[str(metrics.get("instanceName", metrics_path.parent.name))] = metrics
    rows = []
    for row in certification.get("results", []):
        if row.get("suite") != "grubhub-mdrplib":
            continue
        merged = dict(row)
        merged.update(metrics_by_instance.get(str(row.get("instance")), {}))
        rows.append(merged)
    if not rows:
        return {"schemaVersion": "food-dispatch-quality/v1", "finalVerdict": "EVIDENCE_GAP", "verdictReasons": ["mdrplib-missing"], "layers": []}
    layers = [score_food(rows), score_driver(rows), score_anchor(rows), score_sequence(rows, "pickupSequenceQuality"), score_sequence(rows, "dropoffSequenceQuality"), score_order_to_delivery(rows)]
    if any(item["verdict"] == "FAIL" for item in layers):
        final = "FAIL"
    elif all(item["verdict"] == "PASS" for item in layers):
        final = "PASS"
    else:
        final = "PASS_WITH_LIMITS"
    explainability = {
        "worstInstancesByP95Delay": top_instances(rows, "p95Delay"),
        "worstInstancesByFoodOnVehicle": top_instances(rows, "p95FoodOnVehicleTime"),
        "worstInstancesByOrderToDelivery": top_instances(rows, "p95OrderToDeliveryTime"),
        "worstInstancesByFairnessGini": top_instances(rows, "assignmentFairnessGini"),
        "layerContribution": [{"layer": item["layer"], "score": item["score"], "blockers": item.get("blockers", [])} for item in layers],
        "recommendations": recommendations(layers),
    }
    return {"schemaVersion": "food-dispatch-quality/v1", "benchmarkFamily": "grubhub-mdrplib-quality-thresholds", "sourceCertification": str(certification_path), "rowCount": len(rows), "finalVerdict": final, "layers": layers, "explainability": explainability}


def markdown(result: Dict[str, Any]) -> str:
    lines = ["# Food Dispatch Quality Benchmark", "", f"FINAL_VERDICT = {result['finalVerdict']}", "", "| Layer | Score | Verdict | Blockers |", "| --- | ---: | --- | --- |"]
    for item in result.get("layers", []):
        lines.append(f"| `{item['layer']}` | `{item['score']:.3f}` | `{item['verdict']}` | `{', '.join(item.get('blockers', [])) or 'none'}` |")
    lines.extend(["", "## Recommendations", ""])
    for item in result.get("explainability", {}).get("recommendations", []):
        lines.append(f"- `{item['blocker']}`: {item['recommendedOptimizationTarget']}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build food/driver/anchor/sequence quality evidence from MDRPLib certification rows.")
    parser.add_argument("--certification-root", default=str(DEFAULT_CERTIFICATION_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    result = build_quality(Path(args.certification_root))
    write_json(output_root / "food_dispatch_quality_results.json", result)
    (output_root / "food_dispatch_quality_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[FOOD DISPATCH QUALITY JSON] {output_root / 'food_dispatch_quality_results.json'}")
    print(f"[FOOD DISPATCH QUALITY REPORT] {output_root / 'food_dispatch_quality_report.md'}")
    return 1 if result["finalVerdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CERTIFICATION_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "certification-suite"

SCORE_GROUPS = (
    "feasibility",
    "optimality",
    "foodDeliveryQuality",
    "dynamicQuality",
    "roadRealism",
    "systemReliability",
)

LAYER_BY_STAGE = {
    "A-academic-correctness": "academic-correctness",
    "B-scale": "academic-scale",
    "C-food-delivery-official": "food-delivery-public",
    "D-dynamic-official": "dynamic-dispatch",
    "D-dynamic-stress": "dynamic-stress",
    "E-hcm-road-native": "hcm-road-native",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def verdict_from_score(score: float, blockers: Sequence[str]) -> str:
    if any(blocker.startswith("hard-") or blocker.endswith("-violation") for blocker in blockers):
        return "FAIL"
    if "evidence-gap" in blockers:
        return "EVIDENCE_GAP"
    if score >= 0.90 and not blockers:
        return "PASS"
    return "PASS_WITH_LIMITS"


def average(values: Iterable[float], default: float = 1.0) -> float:
    values = list(values)
    return mean(values) if values else default


def hard_violation_count(row: dict[str, Any]) -> int:
    return sum(int(row.get(key, 0) or 0) for key in (
        "capacityViolationCount",
        "timeWindowViolationCount",
        "pickupBeforeDropoffViolationCount",
        "activeRouteCorruptionCount",
        "vehicleStateContinuityViolation",
        "pickupBeforeReadyTimeViolation",
        "courierShiftViolation",
        "foodOnVehicleHardViolation",
    ))


def feasibility_score(rows: Sequence[dict[str, Any]]) -> tuple[float, list[str]]:
    blockers: list[str] = []
    has_fail = any(row.get("verdict") == "FAIL" for row in rows)
    evidence_gap_count = sum(1 for row in rows if row.get("verdict") == "EVIDENCE_GAP")
    if has_fail:
        blockers.append("hard-fail-row")
    if evidence_gap_count:
        blockers.append("evidence-gap")
    violations = sum(hard_violation_count(row) for row in rows)
    if violations:
        blockers.append("hard-constraint-violation")
    if has_fail or violations:
        return 0.0, blockers
    if not rows:
        return 1.0, blockers
    return 1.0 - evidence_gap_count / len(rows), blockers


def optimality_score(rows: Sequence[dict[str, Any]]) -> tuple[float, list[str]]:
    blockers: list[str] = []
    scored: list[float] = []
    for row in rows:
        if row.get("verdict") == "EVIDENCE_GAP":
            blockers.append("evidence-gap")
            scored.append(0.0)
            continue
        best_vehicles = row.get("bestKnownVehicleCount")
        vehicles = row.get("vehicleCount")
        if best_vehicles and vehicles:
            gap = max(0.0, (float(vehicles) - float(best_vehicles)) / max(1.0, float(best_vehicles)))
            if gap > 0:
                blockers.append("vehicle-count-gap")
            scored.append(clamp(1.0 - gap))
        gap_percent = row.get("objectiveGapPercent")
        if gap_percent is not None:
            scored.append(clamp(1.0 - max(0.0, float(gap_percent)) / 20.0))
        if "runtime-timeout" in row.get("verdictReasons", []):
            blockers.append("runtime-timeout")
            scored.append(0.0)
    return average(scored), sorted(set(blockers))


def food_delivery_score(rows: Sequence[dict[str, Any]]) -> tuple[float, list[str]]:
    blockers: list[str] = []
    scored: list[float] = []
    for row in rows:
        if row.get("verdict") == "EVIDENCE_GAP":
            blockers.append("evidence-gap")
            scored.append(0.0)
            continue
        served = row.get("servedOrderRate")
        if served is not None:
            scored.append(clamp(float(served)))
            if float(served) < 0.95:
                blockers.append("served-rate-low")
        late = row.get("lateOrderRate")
        if late is not None:
            scored.append(clamp(1.0 - float(late)))
            if float(late) > 0.05:
                blockers.append("late-rate-high")
        if "mdrplib-official-structural-baseline" in row.get("verdictReasons", []):
            blockers.append("food-baseline-only")
            scored.append(0.75)
    return average(scored), sorted(set(blockers))


def dynamic_score(rows: Sequence[dict[str, Any]]) -> tuple[float, list[str]]:
    blockers: list[str] = []
    scored: list[float] = []
    for row in rows:
        if row.get("verdict") == "EVIDENCE_GAP":
            blockers.append("evidence-gap")
            scored.append(0.0)
            continue
        stability = row.get("routeStabilityScore")
        if stability is not None:
            scored.append(clamp(float(stability)))
            if float(stability) < 0.90:
                blockers.append("route-stability-low")
        replan_latency = row.get("maxReplanLatencyMs")
        if replan_latency is not None:
            scored.append(clamp(1.0 - float(replan_latency) / 1_000.0))
            if float(replan_latency) > 1_000.0:
                blockers.append("replan-latency-high")
        if any(reason.startswith("icaps-deterministic-rolling-horizon-baseline") for reason in row.get("verdictReasons", [])):
            blockers.append("dynamic-baseline-only")
            scored.append(0.80)
    return average(scored), sorted(set(blockers))


def road_realism_score(rows: Sequence[dict[str, Any]]) -> tuple[float, list[str]]:
    blockers: list[str] = []
    scored: list[float] = []
    for row in rows:
        route_fallback = row.get("routeFallbackRate")
        if route_fallback is not None:
            scored.append(clamp(1.0 - float(route_fallback)))
            if float(route_fallback) > 0.0:
                blockers.append("route-fallback-used")
        covered = row.get("coveredOrderCount")
        if covered is not None and int(covered or 0) <= 0:
            blockers.append("hcm-coverage-zero")
            scored.append(0.0)
        assignments = row.get("executedAssignmentCount")
        if assignments is not None and int(assignments or 0) <= 0:
            blockers.append("hcm-assignment-zero")
            scored.append(0.0)
    return average(scored), sorted(set(blockers))


def system_reliability_score(rows: Sequence[dict[str, Any]], preflight: dict[str, Any] | None) -> tuple[float, list[str]]:
    blockers: list[str] = []
    scored: list[float] = []
    if preflight:
        if preflight.get("verdict") != "PASS":
            blockers.append("preflight-not-pass")
            scored.append(0.0)
        else:
            scored.append(1.0)
        for worker in preflight.get("workers", {}).get("workers", []):
            if not worker.get("ready"):
                blockers.append(f"worker-not-ready-{worker.get('name')}")
                scored.append(0.0)
            else:
                scored.append(1.0)
            version = worker.get("version", {})
            if worker.get("name") == "greedrl" and version.get("runtimeMode") == "lite":
                blockers.append("greedrl-lite-runtime")
                scored.append(0.5)
    for row in rows:
        fallback = row.get("workerFallbackRate")
        if fallback is not None:
            scored.append(clamp(1.0 - float(fallback)))
            if float(fallback) >= 1.0:
                blockers.append("worker-fallback-total")
        if row.get("greedrlRuntimeMode") == "lite":
            blockers.append("greedrl-lite-runtime")
            scored.append(0.5)
    return average(scored), sorted(set(blockers))


def primary_blocker(blockers: Sequence[str], fallback: str) -> str:
    priority = (
        "hard-fail-row",
        "hard-constraint-violation",
        "evidence-gap",
        "vehicle-count-gap",
        "runtime-timeout",
        "hcm-coverage-zero",
        "hcm-assignment-zero",
        "route-fallback-used",
        "preflight-not-pass",
        "greedrl-lite-runtime",
        "worker-fallback-total",
        "food-baseline-only",
        "dynamic-baseline-only",
    )
    for item in priority:
        if item in blockers:
            return item
    return blockers[0] if blockers else fallback


def recommended_lane(blocker: str) -> str:
    return {
        "evidence-gap": "data-closure",
        "vehicle-count-gap": "academic-global-consolidation",
        "runtime-timeout": "solver-runtime-budget",
        "food-baseline-only": "food-delivery-objective",
        "dynamic-baseline-only": "dynamic-replan-policy",
        "route-fallback-used": "road-native-quality",
        "hcm-coverage-zero": "hcm-plan-selection",
        "hcm-assignment-zero": "hcm-plan-selection",
        "greedrl-lite-runtime": "worker-runtime-stability",
        "preflight-not-pass": "system-reliability",
    }.get(blocker, "monitor")


def layer_rows(rows: Sequence[dict[str, Any]], layer: str) -> list[dict[str, Any]]:
    return [row for row in rows if LAYER_BY_STAGE.get(row.get("stage"), row.get("stage")) == layer]


def score_layer(layer: str, rows: Sequence[dict[str, Any]], preflight: dict[str, Any] | None) -> dict[str, Any]:
    feasibility, feasibility_blockers = feasibility_score(rows)
    optimality, optimality_blockers = optimality_score(rows)
    food, food_blockers = food_delivery_score(rows)
    dynamic, dynamic_blockers = dynamic_score(rows)
    road, road_blockers = road_realism_score(rows)
    system, system_blockers = system_reliability_score(rows, preflight if layer == "hcm-road-native" else None)
    scores = {
        "feasibility": feasibility,
        "optimality": optimality,
        "foodDeliveryQuality": food,
        "dynamicQuality": dynamic,
        "roadRealism": road,
        "systemReliability": system,
    }
    blockers = sorted(set(
        feasibility_blockers
        + optimality_blockers
        + food_blockers
        + dynamic_blockers
        + road_blockers
        + system_blockers
    ))
    score = average(scores.values())
    blocker = primary_blocker(blockers, "none")
    return {
        "layer": layer,
        "score": score,
        "scores": scores,
        "verdict": verdict_from_score(score, blockers),
        "mainBlocker": blocker,
        "recommendedLane": recommended_lane(blocker),
        "blockers": blockers,
        "rowCount": len(rows),
    }


def load_preflight(certification_root: Path, full_system_root: Path | None) -> dict[str, Any] | None:
    candidates = []
    if full_system_root is not None:
        candidates.append(full_system_root / "preflight_result.json")
    candidates.append(certification_root.parent / "full-system-e2e" / "preflight_result.json")
    for path in candidates:
        if path.exists():
            return read_json(path)
    return None


def build_scorecard(certification_root: Path, full_system_root: Path | None = None) -> dict[str, Any]:
    result_path = certification_root / "certification_suite_results.json"
    certification = read_json(result_path)
    rows = certification.get("results", [])
    preflight = load_preflight(certification_root, full_system_root)
    layers = sorted(set(LAYER_BY_STAGE.get(row.get("stage"), row.get("stage")) for row in rows))
    layer_scores = [score_layer(layer, layer_rows(rows, layer), preflight) for layer in layers]
    overall_score = average(layer["score"] for layer in layer_scores)
    overall_blocker = primary_blocker([layer["mainBlocker"] for layer in layer_scores if layer["mainBlocker"] != "none"], "none")
    overall_verdict = "FAIL" if any(layer["verdict"] == "FAIL" for layer in layer_scores) else (
        "PASS_WITH_LIMITS" if any(layer["verdict"] in {"PASS_WITH_LIMITS", "EVIDENCE_GAP"} for layer in layer_scores) else "PASS"
    )
    return {
        "schemaVersion": "dispatch-certification-scorecard/v1",
        "sourceCertification": str(result_path),
        "certificationVerdict": certification.get("finalVerdict"),
        "overallScore": overall_score,
        "overallVerdict": overall_verdict,
        "mainBlocker": overall_blocker,
        "recommendedLane": recommended_lane(overall_blocker),
        "layers": layer_scores,
    }


def markdown(scorecard: dict[str, Any]) -> str:
    lines = [
        "# Dispatch Certification Scorecard",
        "",
        f"- overall verdict: `{scorecard['overallVerdict']}`",
        f"- overall score: `{scorecard['overallScore']:.3f}`",
        f"- main blocker: `{scorecard['mainBlocker']}`",
        f"- recommended lane: `{scorecard['recommendedLane']}`",
        "",
        "| Layer | Score | Verdict | Main blocker | Recommended lane | Rows |",
        "| --- | ---: | --- | --- | --- | ---: |",
    ]
    for layer in scorecard.get("layers", []):
        lines.append(
            f"| `{layer['layer']}` | `{layer['score']:.3f}` | `{layer['verdict']}` | "
            f"`{layer['mainBlocker']}` | `{layer['recommendedLane']}` | `{layer['rowCount']}` |"
        )
    lines.extend(["", "## Score Groups", ""])
    for layer in scorecard.get("layers", []):
        scores = ", ".join(f"{key}={value:.3f}" for key, value in layer["scores"].items())
        blockers = ", ".join(layer.get("blockers", [])) or "none"
        lines.append(f"- `{layer['layer']}`: {scores}; blockers: `{blockers}`")
    return "\n".join(lines) + "\n"


def write_scorecard(certification_root: Path, full_system_root: Path | None = None) -> tuple[Path, Path]:
    scorecard = build_scorecard(certification_root, full_system_root)
    json_path = certification_root / "certification_scorecard.json"
    markdown_path = certification_root / "certification_scorecard.md"
    write_json(json_path, scorecard)
    markdown_path.write_text(markdown(scorecard), encoding="utf-8")
    return json_path, markdown_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a unified scorecard from Dispatch certification artifacts.")
    parser.add_argument("--certification-root", default=str(DEFAULT_CERTIFICATION_ROOT))
    parser.add_argument("--full-system-root", default="")
    args = parser.parse_args(argv)
    full_system_root = Path(args.full_system_root) if args.full_system_root else None
    json_path, markdown_path = write_scorecard(Path(args.certification_root), full_system_root)
    print(f"[CERTIFICATION SCORECARD JSON] {json_path}")
    print(f"[CERTIFICATION SCORECARD REPORT] {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

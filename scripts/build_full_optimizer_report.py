from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def load_optional(path_text: str | None, missing: list[str]) -> dict[str, Any] | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.exists():
        missing.append(str(path))
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ablation_ml_disabled(ablation: dict[str, Any] | None) -> bool:
    if not ablation:
        return False
    variants = {variant.get("variantId"): variant for variant in ablation.get("variants", [])}
    return all(variants.get(key, {}).get("status") == "disabled-by-policy" for key in ("A6", "A7", "A8"))


def best_ablation_variant(ablation: dict[str, Any] | None) -> str:
    if not ablation:
        return ""
    return str(ablation.get("bestVariantId", ""))


def enabled_ablation_variants(ablation: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [variant for variant in (ablation or {}).get("variants", []) if variant.get("status") == "enabled"]


def fallback_rate_summary(ablation: dict[str, Any] | None) -> dict[str, Any]:
    variants = enabled_ablation_variants(ablation)
    fallback_rates = [float(variant.get("fallbackRate") or 0.0) for variant in variants if variant.get("fallbackRate") is not None]
    best_variant_id = best_ablation_variant(ablation)
    best_variant = next((variant for variant in variants if variant.get("variantId") == best_variant_id), None)
    current_rate = float((best_variant or {}).get("fallbackRate") or 0.0)
    return {
        "currentVariantId": best_variant_id,
        "currentFallbackRate": current_rate,
        "maxFallbackRate": max(fallback_rates) if fallback_rates else 0.0,
    }


def parse_dispatch_summary(dispatch_summary: str | None) -> dict[str, Any]:
    if not dispatch_summary:
        return {}
    try:
        payload = json.loads(dispatch_summary)
    except json.JSONDecodeError:
        return {"rawText": dispatch_summary[:2000]}
    if isinstance(payload, dict):
        return payload
    return {}


def runtime_profile(dispatch_summary: dict[str, Any] | None) -> dict[str, Any]:
    dispatch_summary = dispatch_summary or {}
    selector = dispatch_summary.get("selectorTelemetry") if isinstance(dispatch_summary.get("selectorTelemetry"), dict) else {}
    repair = dispatch_summary.get("activeRepair") if isinstance(dispatch_summary.get("activeRepair"), dict) else {}
    stages = dispatch_summary.get("stageLatencies") if isinstance(dispatch_summary.get("stageLatencies"), dict) else {}
    stage_fallbacks = dispatch_summary.get("stageFallbackSummary") if isinstance(dispatch_summary.get("stageFallbackSummary"), dict) else {}
    return {
        "selectorTimedOut": bool(selector.get("timedOut", False)),
        "selectorFallbackLevel": str(selector.get("fallbackLevel", "NONE")),
        "selectorPoolInputCount": int(selector.get("poolInputCount", 0) or 0),
        "selectorPoolReducedCount": int(selector.get("poolReducedCount", 0) or 0),
        "selectorPoolRejectedCount": int(selector.get("poolRejectedCount", 0) or 0),
        "selectorMaxPoolSize": int(selector.get("selectorMaxPoolSize", 0) or 0),
        "selectorPoolCapApplied": bool(selector.get("selectorPoolCapApplied", False)),
        "selectorPoolCapObjectiveLoss": float(selector.get("selectorPoolCapObjectiveLoss", 0.0) or 0.0),
        "repairTimedOut": bool(repair.get("timedOut", False)),
        "repairRuntimeMs": int(repair.get("runtimeMs", 0) or 0),
        "repairOperatorsTried": int(repair.get("operatorsTried", 0) or 0),
        "stageLatencies": stages,
        "stageFallbacks": stage_fallbacks,
    }


def bottleneck(rank: int, component: str, severity: str, reason: str, evidence: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "rank": rank,
        "component": component,
        "severity": severity,
        "reason": reason,
        "evidence": evidence,
        "recommendedAction": action,
    }


def rank_bottlenecks(academic: dict[str, Any] | None, ablation: dict[str, Any] | None, missing_inputs: list[str], runtime: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    strong_gap = float((academic or {}).get("strong_baseline_gap", 0.0) or 0.0)
    vehicle_gap = int((academic or {}).get("vehicle_count_gap", 0) or 0)
    if academic is None:
        items.append(bottleneck(0, "academic-gap", "HIGH", "academic solver report missing", {"missing": True}, "run academic solver bridge and compare gap"))
    elif strong_gap > 0.05 or vehicle_gap > 0:
        items.append(bottleneck(0, "academic-gap", "HIGH", "strong baseline or vehicle count gap remains positive", {"strongBaselineGap": strong_gap, "vehicleCountGap": vehicle_gap}, "improve route consolidation, HGS bridge, and SP post-optimization"))
    else:
        items.append(bottleneck(0, "academic-gap", "LOW", "academic gap is currently bounded", {"strongBaselineGap": strong_gap, "vehicleCountGap": vehicle_gap}, "keep academic bridge as regression guard"))

    enabled_variants = enabled_ablation_variants(ablation)
    if ablation is None:
        items.append(bottleneck(0, "ablation", "HIGH", "optimizer ablation missing", {"missing": True}, "run A0-A8 ablation before claiming improvements"))
    elif enabled_variants:
        best = max(enabled_variants, key=lambda variant: float(variant.get("qualityScore") or 0.0))
        a5 = next((variant for variant in enabled_variants if variant.get("variantId") == "A5"), None)
        if a5 and best.get("variantId") != "A5":
            items.append(bottleneck(0, "selector", "MEDIUM", "A5 is not best enabled variant", {"bestVariant": best.get("variantId"), "a5Quality": a5.get("qualityScore")}, "inspect selector objective and pool reducer before adding ML"))
        else:
            items.append(bottleneck(0, "selector", "LOW", "A5 selector stack is best or tied among enabled variants", {"bestVariant": best.get("variantId")}, "keep selector telemetry gates active"))
        fallback_summary = fallback_rate_summary(ablation)
        current_fallback = float(fallback_summary["currentFallbackRate"])
        if current_fallback > 0.10:
            items.append(bottleneck(0, "runtime", "MEDIUM", "current best variant fallback rate remains above target", fallback_summary, "profile stage latency and shrink candidate/repair budgets under pressure"))
        else:
            items.append(bottleneck(0, "runtime", "LOW", "current best variant fallback rate is within target", fallback_summary, "keep runtime/fallback telemetry as regression guard"))
    runtime = runtime or {}
    if runtime.get("selectorTimedOut"):
        items.append(bottleneck(0, "selector-runtime", "MEDIUM", "selector timed out and returned incumbent/fallback", runtime, "reduce selector pool cap before CP-SAT and keep incumbent fallback enabled"))
    if runtime.get("repairTimedOut"):
        items.append(bottleneck(0, "repair-runtime", "MEDIUM", "active repair exhausted its bounded budget", runtime, "limit ALNS operators by remaining budget and prioritize deadline/freshness operators"))
    if runtime.get("selectorPoolCapApplied") and float(runtime.get("selectorPoolCapObjectiveLoss", 0.0) or 0.0) > 0.0:
        items.append(bottleneck(0, "pool-reducer", "MEDIUM", "pool cap removed objective-leading candidate", runtime, "increase diversity quota or max pool only for high-loss ticks"))
    if ablation and ablation_ml_disabled(ablation):
        items.append(bottleneck(0, "ml", "LOW", "A6-A8 are disabled by policy and make no value claim", {"mlValueClaim": ablation.get("mlValueClaim", False)}, "do not tune ML until solver-first A5 baseline is stronger"))

    if missing_inputs:
        items.append(bottleneck(0, "evidence", "MEDIUM", "one or more optional inputs are missing", {"missingInputs": missing_inputs}, "rerun missing benchmark rails for complete diagnosis"))

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    ranked = sorted(items, key=lambda item: (severity_order.get(item["severity"], 9), item["component"]))
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked


def next_recommendation(bottlenecks: list[dict[str, Any]]) -> str:
    first = bottlenecks[0] if bottlenecks else None
    if not first:
        return "keep monitoring optimizer gates"
    if first.get("severity") == "LOW":
        return "no blocking bottleneck; keep monitoring optimizer gates and rerun with dispatch summary when available"
    if first["component"] == "academic-gap":
        return "prioritize academic route consolidation and stronger HGS/SP post-optimization evidence"
    if first["component"] == "runtime":
        return "prioritize quality-per-millisecond profiling and candidate pool budget controls"
    if first["component"] == "selector":
        return "prioritize selector objective tuning and reduced-pool diagnostics"
    if first["component"] == "ablation":
        return "run optimizer ablation A0-A8 before starting new algorithm work"
    return str(first["recommendedAction"])


def build_report(academic: dict[str, Any] | None, ablation: dict[str, Any] | None, dispatch_summary: str | None, missing_inputs: list[str]) -> dict[str, Any]:
    dispatch_payload = parse_dispatch_summary(dispatch_summary)
    runtime = runtime_profile(dispatch_payload)
    bottlenecks = rank_bottlenecks(academic, ablation, missing_inputs, runtime)
    llm_disabled = ablation_ml_disabled(ablation)
    gates = {
        "academicBridgePass": academic is not None,
        "ablationPass": ablation is not None and {variant.get("variantId") for variant in ablation.get("variants", [])} >= {f"A{index}" for index in range(9)},
        "runtimePass": not any(item["component"] == "runtime" and item["severity"] == "HIGH" for item in bottlenecks),
        "qualityPass": academic is not None and float(academic.get("strong_baseline_gap", 0.0) or 0.0) <= 0.05,
        "llmDisabled": llm_disabled,
    }
    return {
        "schemaVersion": "full-optimizer-report/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "missingInputs": missing_inputs,
        "inputs": {
            "academicSolverReport": bool(academic),
            "ablationResults": bool(ablation),
            "dispatchSummary": bool(dispatch_summary),
        },
        "quality": {
            "vehicleCountGap": int((academic or {}).get("vehicle_count_gap", 0) or 0),
            "distanceGapPct": float((academic or {}).get("distance_gap_pct", 0.0) or 0.0),
            "strongBaselineGap": float((academic or {}).get("strong_baseline_gap", 0.0) or 0.0),
            "bestAblationVariant": best_ablation_variant(ablation),
            "mlValueClaim": bool((ablation or {}).get("mlValueClaim", False)),
        },
        "runtime": {
            **fallback_rate_summary(ablation),
            "runtimeToBestMs": int((academic or {}).get("runtime_to_best_ms", 0) or 0),
            "profile": runtime,
        },
        "bottlenecks": bottlenecks,
        "gates": gates,
        "nextRecommendation": next_recommendation(bottlenecks),
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full Optimizer Report",
        "",
        "## Verdict",
        "",
        f"- overall: `{'PASS' if all(report['gates'].values()) else 'PASS_WITH_LIMITS'}`",
        f"- next recommendation: {report['nextRecommendation']}",
        "",
        "## Quality",
        "",
        f"- vehicle count gap: `{report['quality']['vehicleCountGap']}`",
        f"- distance gap pct: `{report['quality']['distanceGapPct']}`",
        f"- strong baseline gap: `{report['quality']['strongBaselineGap']}`",
        f"- best ablation variant: `{report['quality']['bestAblationVariant']}`",
        f"- ML value claim: `{report['quality']['mlValueClaim']}`",
        "",
        "## Bottleneck Ranking",
        "",
        "| Rank | Component | Severity | Reason | Recommended action |",
        "|---:|---|---|---|---|",
    ]
    for item in report["bottlenecks"]:
        lines.append(f"| {item['rank']} | {item['component']} | {item['severity']} | {item['reason']} | {item['recommendedAction']} |")
    lines.extend(["", "## Gates", "", "| Gate | Status |", "|---|---|"])
    for key, value in report["gates"].items():
        lines.append(f"| {key} | `{value}` |")
    lines.append("")
    return "\n".join(lines)


def write_outputs(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "full_optimizer_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "full_optimizer_report.md").write_text(markdown(report), encoding="utf-8")
    (output_dir / "bottleneck_ranking.json").write_text(json.dumps(report["bottlenecks"], indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "bottleneck_ranking.md").write_text(markdown({**report, "gates": report["gates"]}), encoding="utf-8")
    (output_dir / "benchmark_manifest.json").write_text(json.dumps({"schemaVersion": "benchmark-manifest/v1", "createdAt": report["createdAt"], "missingInputs": report["missingInputs"]}, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build full optimizer benchmark and bottleneck report.")
    parser.add_argument("--academic-report")
    parser.add_argument("--ablation-results")
    parser.add_argument("--dispatch-summary")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    missing: list[str] = []
    academic = load_optional(args.academic_report, missing)
    ablation = load_optional(args.ablation_results, missing)
    dispatch_summary = None
    if args.dispatch_summary:
        path = Path(args.dispatch_summary)
        if path.exists():
            dispatch_summary = path.read_text(encoding="utf-8")
        else:
            missing.append(str(path))
    report = build_report(academic, ablation, dispatch_summary, missing)
    write_outputs(Path(args.output_dir), report)
    print(f"[FULL REPORT] wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

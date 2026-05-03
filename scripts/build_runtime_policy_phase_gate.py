from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def obj(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def number(payload: dict[str, Any], key: str) -> float:
    try:
        return float(payload.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def nested_number(payload: dict[str, Any], section: str, key: str) -> float:
    return number(obj(payload, section), key)


def summarize_artifact(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    control_metrics = obj(payload, "controlMetrics")
    variant_metrics = obj(payload, "variantMetrics")
    control_runtime = obj(payload, "controlRuntimeTelemetry")
    variant_runtime = obj(payload, "variantRuntimeTelemetry")
    control_selector = obj(control_runtime, "selectorTelemetry")
    variant_selector = obj(variant_runtime, "selectorTelemetry")
    control_route_budget = obj(control_runtime, "routeProposalBudget")
    variant_route_budget = obj(variant_runtime, "routeProposalBudget")

    control_latency = number(control_runtime, "totalDispatchLatencyMs")
    variant_latency = number(variant_runtime, "totalDispatchLatencyMs")
    control_objective = number(control_metrics, "selectorObjectiveValue")
    variant_objective = number(variant_metrics, "selectorObjectiveValue")
    control_fallback = number(control_metrics, "routeFallbackRate")
    variant_fallback = number(variant_metrics, "routeFallbackRate")
    control_pool = nested_number(control_selector, "", "poolReducedCount") if False else number(control_selector, "poolReducedCount")
    variant_pool = number(variant_selector, "poolReducedCount")
    control_route_after = number(control_route_budget, "candidateCountAfterBudget")
    variant_route_after = number(variant_route_budget, "candidateCountAfterBudget")

    blockers: list[str] = []
    if not bool(control_runtime.get("runtimePolicyApplied")):
        blockers.append("runtime-policy-not-applied")
    if control_latency > variant_latency:
        blockers.append("runtime-policy-latency-not-reduced")
    if control_objective + 0.25 < variant_objective:
        blockers.append("runtime-policy-objective-regressed")
    if control_fallback > variant_fallback:
        blockers.append("runtime-policy-fallback-regressed")
    if bool(control_runtime.get("totalBudgetBreached")) and not bool(variant_runtime.get("totalBudgetBreached")):
        blockers.append("runtime-policy-budget-breached")
    if control_pool > variant_pool and variant_pool > 0:
        blockers.append("runtime-policy-selector-pool-not-reduced")
    if control_route_after > variant_route_after and variant_route_after > 0:
        blockers.append("runtime-policy-route-budget-not-reduced")

    return {
        "artifactPath": str(path),
        "scenarioPack": payload.get("scenarioPack"),
        "workloadSize": payload.get("workloadSize"),
        "executionMode": payload.get("executionMode"),
        "runtimePolicyApplied": bool(control_runtime.get("runtimePolicyApplied")),
        "controlLatencyMs": control_latency,
        "variantLatencyMs": variant_latency,
        "latencyDeltaMs": round(control_latency - variant_latency, 9),
        "controlSelectorObjectiveValue": control_objective,
        "variantSelectorObjectiveValue": variant_objective,
        "selectorObjectiveDelta": round(control_objective - variant_objective, 9),
        "controlRouteFallbackRate": control_fallback,
        "variantRouteFallbackRate": variant_fallback,
        "controlPoolReducedCount": control_pool,
        "variantPoolReducedCount": variant_pool,
        "controlRouteCandidateAfterBudget": control_route_after,
        "variantRouteCandidateAfterBudget": variant_route_after,
        "blockers": blockers,
        "pass": not blockers,
    }


def build_report(input_dir: Path) -> dict[str, Any]:
    artifacts = sorted(input_dir.glob("dispatch-quality-ablation-runtime-policy-*.json"))
    rows = [summarize_artifact(path) for path in artifacts]
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    return {
        "schemaVersion": "runtime-policy-phase-gate/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "inputDir": str(input_dir),
        "rowCount": len(rows),
        "rows": rows,
        "blockers": blockers,
        "pass": bool(rows) and not blockers,
    }


def markdown(report: dict[str, Any]) -> str:
    verdict = "PASS" if report["pass"] else "FAIL"
    lines = [
        "# Runtime Policy Phase Gate",
        "",
        f"- verdict: `{verdict}`",
        f"- rows: `{report['rowCount']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Scenario | Size | Runtime On/Off | Obj Delta | Pool On/Off | Route Budget On/Off | Fallback On/Off | Blockers |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['scenarioPack']} | {row['workloadSize']} | "
            f"{row['controlLatencyMs']}/{row['variantLatencyMs']} | {row['selectorObjectiveDelta']} | "
            f"{row['controlPoolReducedCount']}/{row['variantPoolReducedCount']} | "
            f"{row['controlRouteCandidateAfterBudget']}/{row['variantRouteCandidateAfterBudget']} | "
            f"{row['controlRouteFallbackRate']}/{row['variantRouteFallbackRate']} | {row['blockers']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build runtime policy phase gate from ablation artifacts.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    report = build_report(Path(args.input_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "runtime_policy_phase_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "runtime_policy_phase_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[RUNTIME POLICY PHASE GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

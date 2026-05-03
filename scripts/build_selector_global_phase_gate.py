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


def text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def summarize_artifact(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    control_metrics = obj(payload, "controlMetrics")
    variant_metrics = obj(payload, "variantMetrics")
    control_runtime = obj(payload, "controlRuntimeTelemetry")
    variant_runtime = obj(payload, "variantRuntimeTelemetry")
    control_selector = obj(control_runtime, "selectorTelemetry")
    variant_selector = obj(variant_runtime, "selectorTelemetry")
    control_source = obj(payload, "controlSelectorSourceSummary")

    control_objective = number(control_metrics, "selectorObjectiveValue")
    variant_objective = number(variant_metrics, "selectorObjectiveValue")
    control_latency = number(control_runtime, "totalDispatchLatencyMs")
    variant_latency = number(variant_runtime, "totalDispatchLatencyMs")
    control_fallback = number(control_metrics, "routeFallbackRate")
    variant_fallback = number(variant_metrics, "routeFallbackRate")
    control_pool_input = number(control_selector, "poolInputCount")
    control_pool_reduced = number(control_selector, "poolReducedCount")
    control_selected_ml = number(control_source, "selectedMlRouteCandidateCount")
    control_selected_greedrl = number(control_source, "selectedGreedRlCandidateCount")

    blockers: list[str] = []
    if text(payload, "toggledComponent") != "selector-global":
        blockers.append("selector-global-wrong-component")
    if text(control_selector, "mode") not in {"MINI_EXACT", "ORTOOLS", "GREEDY_REPAIR"}:
        blockers.append("selector-global-mode-not-recognized")
    if text(control_selector, "fallbackLevel") in {"GLOBAL_SELECTOR_DISABLED", "DEGRADED_GREEDY"}:
        blockers.append("selector-global-fell-back-to-disabled")
    if bool(control_selector.get("timedOut")):
        blockers.append("selector-global-timeout")
    if not bool(control_selector.get("acceptanceGatePassed", True)):
        blockers.append("selector-global-acceptance-gate-failed")
    if control_objective + 0.05 < variant_objective:
        blockers.append("selector-global-objective-regressed")
    if control_fallback > variant_fallback:
        blockers.append("selector-global-fallback-regressed")
    if control_pool_input > 256 and control_pool_reduced >= control_pool_input:
        blockers.append("selector-global-pool-not-reduced")
    if control_pool_reduced > number(control_selector, "selectorMaxPoolSize") and number(control_selector, "selectorMaxPoolSize") > 0:
        blockers.append("selector-global-pool-cap-violated")
    if control_selected_ml + control_selected_greedrl < 1:
        blockers.append("selector-global-no-ml-candidate-selected")
    if control_latency > max(800.0, variant_latency * 2.0):
        blockers.append("selector-global-runtime-too-high")

    return {
        "artifactPath": str(path),
        "scenarioPack": payload.get("scenarioPack"),
        "workloadSize": payload.get("workloadSize"),
        "executionMode": payload.get("executionMode"),
        "controlMode": text(control_selector, "mode"),
        "variantMode": text(variant_selector, "mode"),
        "controlLatencyMs": control_latency,
        "variantLatencyMs": variant_latency,
        "latencyDeltaMs": round(control_latency - variant_latency, 9),
        "controlSelectorObjectiveValue": control_objective,
        "variantSelectorObjectiveValue": variant_objective,
        "selectorObjectiveDelta": round(control_objective - variant_objective, 9),
        "controlPoolInputCount": control_pool_input,
        "controlPoolReducedCount": control_pool_reduced,
        "controlSelectedMlRouteCandidateCount": control_selected_ml,
        "controlSelectedGreedRlCandidateCount": control_selected_greedrl,
        "controlFallbackRate": control_fallback,
        "variantFallbackRate": variant_fallback,
        "blockers": blockers,
        "pass": not blockers,
    }


def build_report(input_dir: Path) -> dict[str, Any]:
    artifacts = sorted(input_dir.glob("dispatch-quality-ablation-selector-global-*.json"))
    rows = [summarize_artifact(path) for path in artifacts]
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    return {
        "schemaVersion": "selector-global-phase-gate/v1",
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
        "# Selector Global Phase Gate",
        "",
        f"- verdict: `{verdict}`",
        f"- rows: `{report['rowCount']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Scenario | Size | Mode On/Off | Runtime On/Off | Obj Delta | Pool In/Reduced | ML Sel | GreedRL Sel | Blockers |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['scenarioPack']} | {row['workloadSize']} | "
            f"{row['controlMode']}/{row['variantMode']} | "
            f"{row['controlLatencyMs']}/{row['variantLatencyMs']} | "
            f"{row['selectorObjectiveDelta']} | "
            f"{row['controlPoolInputCount']}/{row['controlPoolReducedCount']} | "
            f"{row['controlSelectedMlRouteCandidateCount']} | "
            f"{row['controlSelectedGreedRlCandidateCount']} | {row['blockers']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build selector global phase gate from ablation artifacts.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    report = build_report(Path(args.input_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "selector_global_phase_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "selector_global_phase_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[SELECTOR GLOBAL PHASE GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

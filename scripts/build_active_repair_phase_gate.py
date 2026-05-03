from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def number(payload: dict[str, Any], key: str) -> float:
    try:
        return float(payload.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def obj(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def summarize_artifact(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    control_metrics = obj(payload, "controlMetrics")
    variant_metrics = obj(payload, "variantMetrics")
    control_repair = obj(payload, "controlActiveRepairTelemetry")
    variant_repair = obj(payload, "variantActiveRepairTelemetry")

    control_objective = number(control_metrics, "selectorObjectiveValue")
    variant_objective = number(variant_metrics, "selectorObjectiveValue")
    control_completion = number(control_metrics, "averageProjectedCompletionEtaMinutes")
    variant_completion = number(variant_metrics, "averageProjectedCompletionEtaMinutes")
    control_fallback = number(control_metrics, "routeFallbackRate")
    variant_fallback = number(variant_metrics, "routeFallbackRate")
    control_input = int(number(control_repair, "candidateInputCount"))
    control_output = int(number(control_repair, "candidateOutputCount"))
    variant_output = int(number(variant_repair, "candidateOutputCount"))
    operators_tried = int(number(control_repair, "operatorsTried"))
    accepted_moves = int(number(control_repair, "acceptedMoves"))
    improvement = number(control_repair, "bestImprovementDelta")
    runtime_ms = number(control_repair, "runtimeMs")
    frozen_violations = int(number(obj(control_repair, "improvementSummary"), "frozenPrefixViolationCount"))
    food_violations = int(number(obj(control_repair, "improvementSummary"), "foodDurationViolationCount"))

    blockers: list[str] = []
    if control_input <= 0:
        blockers.append("active-repair-no-input-candidates")
    if control_output <= 0:
        blockers.append("active-repair-no-output-candidates")
    if variant_output > 0:
        blockers.append("active-repair-ablation-did-not-disable-repair")
    if operators_tried <= 0:
        blockers.append("active-repair-no-operators-tried")
    if accepted_moves <= 0 and improvement <= 0.0:
        blockers.append("active-repair-no-accepted-improvement")
    if frozen_violations > 0:
        blockers.append("active-repair-frozen-prefix-violation")
    if food_violations > 0:
        blockers.append("active-repair-food-duration-violation")
    if control_fallback > variant_fallback:
        blockers.append("fallback-rate-regressed-with-active-repair")
    if control_objective < variant_objective and control_completion > variant_completion:
        blockers.append("quality-regressed-with-active-repair")
    if runtime_ms > 300.0:
        blockers.append("active-repair-runtime-over-budget")

    return {
        "artifactPath": str(path),
        "scenarioPack": payload.get("scenarioPack"),
        "workloadSize": payload.get("workloadSize"),
        "executionMode": payload.get("executionMode"),
        "controlCandidateInputCount": control_input,
        "controlCandidateOutputCount": control_output,
        "variantCandidateOutputCount": variant_output,
        "operatorsTried": operators_tried,
        "acceptedMoves": accepted_moves,
        "bestImprovementDelta": improvement,
        "runtimeMs": runtime_ms,
        "frozenPrefixViolationCount": frozen_violations,
        "foodDurationViolationCount": food_violations,
        "controlSelectorObjectiveValue": control_objective,
        "variantSelectorObjectiveValue": variant_objective,
        "selectorObjectiveImprovement": round(control_objective - variant_objective, 9),
        "completionEtaDeltaMinutes": round(control_completion - variant_completion, 9),
        "controlRouteFallbackRate": control_fallback,
        "variantRouteFallbackRate": variant_fallback,
        "blockers": blockers,
        "pass": not blockers,
    }


def build_report(input_dir: Path) -> dict[str, Any]:
    artifacts = sorted(input_dir.glob("dispatch-quality-ablation-active-repair-*.json"))
    rows = [summarize_artifact(path) for path in artifacts]
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    return {
        "schemaVersion": "active-repair-phase-gate/v1",
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
        "# Active Repair Phase Gate",
        "",
        f"- verdict: `{verdict}`",
        f"- rows: `{report['rowCount']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Scenario | Size | Repair In/Out | Ops | Accepted | Improve | Runtime | Obj Delta | Completion Delta | Blockers |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['scenarioPack']} | {row['workloadSize']} | "
            f"{row['controlCandidateInputCount']}/{row['controlCandidateOutputCount']} | "
            f"{row['operatorsTried']} | {row['acceptedMoves']} | {row['bestImprovementDelta']} | "
            f"{row['runtimeMs']} | {row['selectorObjectiveImprovement']} | "
            f"{row['completionEtaDeltaMinutes']} | {row['blockers']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build focused active repair phase gate from ablation artifacts.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    report = build_report(Path(args.input_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "active_repair_phase_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "active_repair_phase_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[ACTIVE REPAIR PHASE GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

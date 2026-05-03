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


def metadata_applied(rows: Any, model: str) -> bool:
    if not isinstance(rows, list):
        return False
    return any(
        isinstance(row, dict)
        and row.get("sourceModel") == model
        and row.get("applied") is True
        and row.get("fallbackUsed") is not True
        for row in rows
    )


def summarize_artifact(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    control_metrics = payload.get("controlMetrics") if isinstance(payload.get("controlMetrics"), dict) else {}
    variant_metrics = payload.get("variantMetrics") if isinstance(payload.get("variantMetrics"), dict) else {}
    control_selector = payload.get("controlSelectorSourceSummary") if isinstance(payload.get("controlSelectorSourceSummary"), dict) else {}
    variant_selector = payload.get("variantSelectorSourceSummary") if isinstance(payload.get("variantSelectorSourceSummary"), dict) else {}

    control_objective = number(control_metrics, "selectorObjectiveValue")
    variant_objective = number(variant_metrics, "selectorObjectiveValue")
    control_completion = number(control_metrics, "averageProjectedCompletionEtaMinutes")
    variant_completion = number(variant_metrics, "averageProjectedCompletionEtaMinutes")
    control_pickup = number(control_metrics, "averageProjectedPickupEtaMinutes")
    variant_pickup = number(variant_metrics, "averageProjectedPickupEtaMinutes")
    control_fallback = number(control_metrics, "routeFallbackRate")
    variant_fallback = number(variant_metrics, "routeFallbackRate")
    ml_route_candidates = int(number(control_selector, "mlRouteSelectorCandidateCount"))
    variant_ml_route_candidates = int(number(variant_selector, "mlRouteSelectorCandidateCount"))
    selected_ml_routes = int(number(control_selector, "selectedMlRouteCandidateCount"))
    best_ml_route_score = number(control_selector, "bestMlRouteSelectionScore")
    routefinder_applied = metadata_applied(payload.get("controlMlStageMetadata"), "routefinder-local")

    blockers: list[str] = []
    if not routefinder_applied:
        blockers.append("routefinder-worker-not-applied")
    if ml_route_candidates <= 0:
        blockers.append("ml-route-not-present-in-selector-pool")
    if ml_route_candidates <= variant_ml_route_candidates:
        blockers.append("ml-route-pool-not-expanded")
    if selected_ml_routes <= 0 and control_objective <= variant_objective:
        blockers.append("ml-route-not-selected-or-objective-improved")
    if control_objective <= variant_objective:
        blockers.append("selector-objective-not-improved-with-routefinder")
    if control_completion > variant_completion and control_pickup > variant_pickup:
        blockers.append("eta-quality-regressed-with-routefinder")
    if control_fallback > variant_fallback:
        blockers.append("fallback-rate-regressed-with-routefinder")

    return {
        "artifactPath": str(path),
        "scenarioPack": payload.get("scenarioPack"),
        "workloadSize": payload.get("workloadSize"),
        "executionMode": payload.get("executionMode"),
        "routefinderApplied": routefinder_applied,
        "mlRouteSelectorCandidateCount": ml_route_candidates,
        "variantMlRouteSelectorCandidateCount": variant_ml_route_candidates,
        "selectedMlRouteCandidateCount": selected_ml_routes,
        "bestMlRouteSelectionScore": best_ml_route_score,
        "controlSelectorObjectiveValue": control_objective,
        "variantSelectorObjectiveValue": variant_objective,
        "selectorObjectiveImprovement": round(control_objective - variant_objective, 9),
        "controlCompletionEtaMinutes": control_completion,
        "variantCompletionEtaMinutes": variant_completion,
        "completionEtaDeltaMinutes": round(control_completion - variant_completion, 9),
        "controlPickupEtaMinutes": control_pickup,
        "variantPickupEtaMinutes": variant_pickup,
        "pickupEtaDeltaMinutes": round(control_pickup - variant_pickup, 9),
        "controlRouteFallbackRate": control_fallback,
        "variantRouteFallbackRate": variant_fallback,
        "blockers": blockers,
        "pass": not blockers,
    }


def build_report(input_dir: Path) -> dict[str, Any]:
    artifacts = sorted(input_dir.glob("dispatch-quality-ablation-routefinder-*.json"))
    rows = [summarize_artifact(path) for path in artifacts]
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    return {
        "schemaVersion": "routefinder-phase-gate/v1",
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
        "# RouteFinder Phase Gate",
        "",
        f"- verdict: `{verdict}`",
        f"- rows: `{report['rowCount']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Scenario | Size | ML Route Pool On/Off | Selected ML Route | Obj Delta | Completion Delta | Fallback On/Off | Blockers |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['scenarioPack']} | {row['workloadSize']} | "
            f"{row['mlRouteSelectorCandidateCount']}/{row['variantMlRouteSelectorCandidateCount']} | "
            f"{row['selectedMlRouteCandidateCount']} | {row['selectorObjectiveImprovement']} | "
            f"{row['completionEtaDeltaMinutes']} | {row['controlRouteFallbackRate']}/{row['variantRouteFallbackRate']} | "
            f"{row['blockers']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build focused RouteFinder phase gate from ablation artifacts.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    report = build_report(Path(args.input_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "routefinder_phase_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "routefinder_phase_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[ROUTEFINDER PHASE GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

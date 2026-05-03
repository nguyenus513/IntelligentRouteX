from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Sequence


CORE_COMPONENTS = {"tabular", "forecast"}
HEAVY_COMPONENTS = {"greedrl", "routefinder"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def component_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in payload.get("mlAblationRows", []):
        if not isinstance(row, dict):
            continue
        component = str(row.get("component", "")).strip().lower()
        if not component:
            continue
        rows.append(row)
    return rows


def readiness(payload: dict[str, Any]) -> dict[str, Any]:
    details = payload.get("workerReadinessDetails") if isinstance(payload.get("workerReadinessDetails"), dict) else {}
    ready_by_component = {
        "tabular": bool(payload.get("tabularWorkerImplementationPresent")),
        "forecast": bool(payload.get("forecastWorkerReady")),
        "greedrl": bool(payload.get("greedRlWorkerReady")),
        "routefinder": bool(payload.get("routeFinderWorkerReady")),
    }
    for component, detail in details.items():
        if isinstance(detail, dict) and component in ready_by_component:
            ready_by_component[component] = bool(detail.get("ready"))
    return ready_by_component


def summarize(payload: dict[str, Any], phase: str) -> dict[str, Any]:
    rows = component_rows(payload)
    by_component: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_component[str(row.get("component", "")).lower()].append(row)

    component_summary = {}
    for component, component_rows_ in sorted(by_component.items()):
        robust = [float(row.get("robustUtilityDelta", 0.0) or 0.0) for row in component_rows_]
        selector = [float(row.get("selectorObjectiveDelta", 0.0) or 0.0) for row in component_rows_]
        positives = [row for row in component_rows_ if float(row.get("robustUtilityDelta", 0.0) or 0.0) > 0.0
                     or float(row.get("selectorObjectiveDelta", 0.0) or 0.0) > 0.0]
        component_summary[component] = {
            "rowCount": len(component_rows_),
            "positiveCount": len(positives),
            "meanRobustUtilityDelta": round(mean(robust), 6) if robust else 0.0,
            "meanSelectorObjectiveDelta": round(mean(selector), 6) if selector else 0.0,
            "maxRobustUtilityDelta": round(max(robust), 6) if robust else 0.0,
            "maxSelectorObjectiveDelta": round(max(selector), 6) if selector else 0.0,
        }

    ready_by_component = readiness(payload)
    blockers: list[str] = []
    for component in CORE_COMPONENTS:
        if not ready_by_component.get(component, False):
            blockers.append(f"{component}-not-ready")
    if payload.get("finalVerdict") != "PASS":
        blockers.append("ml-intelligence-not-pass")
    if phase in {"core", "phase2"}:
        for component in CORE_COMPONENTS:
            summary = component_summary.get(component, {})
            if summary.get("rowCount", 0) <= 0:
                blockers.append(f"{component}-missing-ablation-rows")
    if phase in {"greedrl", "phase3"}:
        summary = component_summary.get("greedrl", {})
        if not ready_by_component.get("greedrl", False):
            blockers.append("greedrl-not-ready")
        elif summary.get("rowCount", 0) <= 0:
            blockers.append("greedrl-missing-ablation-rows")
        elif summary.get("positiveCount", 0) <= 0:
            blockers.append("greedrl-positive-contribution-not-proven")
    if phase in {"routefinder", "phase4"}:
        summary = component_summary.get("routefinder", {})
        if not ready_by_component.get("routefinder", False):
            blockers.append("routefinder-not-ready")
        elif summary.get("rowCount", 0) <= 0:
            blockers.append("routefinder-missing-ablation-rows")
        elif summary.get("positiveCount", 0) <= 0:
            blockers.append("routefinder-positive-contribution-not-proven")

    return {
        "schemaVersion": "ml-guided-phase-report/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "sourceFinalVerdict": payload.get("finalVerdict"),
        "mlValueProven": bool(payload.get("mlValueProven")),
        "readyByComponent": ready_by_component,
        "componentSummary": component_summary,
        "coreComponents": sorted(CORE_COMPONENTS),
        "heavyComponents": sorted(HEAVY_COMPONENTS),
        "blockers": blockers,
        "pass": not blockers,
        "passWithLimits": not blockers and not bool(payload.get("mlValueProven")),
    }


def markdown(report: dict[str, Any]) -> str:
    verdict = "PASS" if report["pass"] else "PASS_WITH_LIMITS" if report["passWithLimits"] else "FAIL"
    lines = [
        "# ML Guided Phase Report",
        "",
        f"- verdict: `{verdict}`",
        f"- phase: `{report['phase']}`",
        f"- source final verdict: `{report['sourceFinalVerdict']}`",
        f"- ML value proven: `{report['mlValueProven']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "## Readiness",
        "",
        "| Component | Ready |",
        "|---|---:|",
    ]
    for component, ready in sorted(report["readyByComponent"].items()):
        lines.append(f"| {component} | `{ready}` |")
    lines.extend(["", "## Contribution", "", "| Component | Rows | Positive | Mean Robust Δ | Mean Selector Δ | Max Robust Δ | Max Selector Δ |", "|---|---:|---:|---:|---:|---:|---:|"])
    for component, summary in sorted(report["componentSummary"].items()):
        lines.append(
            f"| {component} | {summary['rowCount']} | {summary['positiveCount']} | "
            f"{summary['meanRobustUtilityDelta']} | {summary['meanSelectorObjectiveDelta']} | "
            f"{summary['maxRobustUtilityDelta']} | {summary['maxSelectorObjectiveDelta']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build ML-guided phase readiness and contribution report.")
    parser.add_argument("--ml-intelligence-results", required=True)
    parser.add_argument("--phase", default="phase2")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    report = summarize(read_json(Path(args.ml_intelligence_results)), args.phase)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ml_guided_phase_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "ml_guided_phase_report.md").write_text(markdown(report), encoding="utf-8")
    print(f"[ML GUIDED PHASE] wrote {output_dir}")
    return 0 if report["pass"] or report["passWithLimits"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

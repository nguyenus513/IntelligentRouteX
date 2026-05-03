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


def summarize_artifact(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    control_metrics = payload.get("controlMetrics") if isinstance(payload.get("controlMetrics"), dict) else {}
    variant_metrics = payload.get("variantMetrics") if isinstance(payload.get("variantMetrics"), dict) else {}
    control_selector = payload.get("controlSelectorSourceSummary") if isinstance(payload.get("controlSelectorSourceSummary"), dict) else {}
    control_bundle = payload.get("controlBundlePoolSummary") if isinstance(payload.get("controlBundlePoolSummary"), dict) else {}

    control_objective = number(control_metrics, "selectorObjectiveValue")
    variant_objective = number(variant_metrics, "selectorObjectiveValue")
    control_bundle_rate = number(control_metrics, "bundleRate")
    variant_bundle_rate = number(variant_metrics, "bundleRate")
    control_max_bundle = number(control_metrics, "maxSelectedBundleSize")
    variant_max_bundle = number(variant_metrics, "maxSelectedBundleSize")
    selected_greedrl = int(number(control_selector, "selectedGreedRlCandidateCount"))
    greedrl_candidates = int(number(control_selector, "greedRlSelectorCandidateCount"))
    source_counts = control_bundle.get("sourceCounts") if isinstance(control_bundle.get("sourceCounts"), dict) else {}

    blockers: list[str] = []
    if source_counts.get("GREEDRL_PROPOSAL", 0) <= 0:
        blockers.append("greedrl-not-retained-in-bundle-pool")
    if greedrl_candidates <= 0:
        blockers.append("greedrl-not-present-in-selector-pool")
    if selected_greedrl <= 0:
        blockers.append("greedrl-not-selected")
    if control_objective <= variant_objective:
        blockers.append("selector-objective-not-improved-with-greedrl")
    if control_bundle_rate <= variant_bundle_rate and control_max_bundle <= variant_max_bundle:
        blockers.append("selected-bundling-not-improved-with-greedrl")

    return {
        "artifactPath": str(path),
        "scenarioPack": payload.get("scenarioPack"),
        "workloadSize": payload.get("workloadSize"),
        "executionMode": payload.get("executionMode"),
        "selectedGreedRlCandidateCount": selected_greedrl,
        "greedRlSelectorCandidateCount": greedrl_candidates,
        "controlSelectorObjectiveValue": control_objective,
        "variantSelectorObjectiveValue": variant_objective,
        "selectorObjectiveImprovement": round(control_objective - variant_objective, 9),
        "controlBundleRate": control_bundle_rate,
        "variantBundleRate": variant_bundle_rate,
        "controlMaxSelectedBundleSize": control_max_bundle,
        "variantMaxSelectedBundleSize": variant_max_bundle,
        "controlSourceCounts": source_counts,
        "blockers": blockers,
        "pass": not blockers,
    }


def build_report(input_dir: Path) -> dict[str, Any]:
    artifacts = sorted(input_dir.glob("dispatch-quality-ablation-greedrl-*.json"))
    rows = [summarize_artifact(path) for path in artifacts]
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    return {
        "schemaVersion": "greedrl-phase-gate/v1",
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
        "# GreedRL Phase Gate",
        "",
        f"- verdict: `{verdict}`",
        f"- rows: `{report['rowCount']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Scenario | Size | Selected GreedRL | GreedRL Pool | Obj Delta | Bundle Rate On/Off | Max Bundle On/Off | Blockers |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['scenarioPack']} | {row['workloadSize']} | {row['selectedGreedRlCandidateCount']} | "
            f"{row['greedRlSelectorCandidateCount']} | {row['selectorObjectiveImprovement']} | "
            f"{row['controlBundleRate']}/{row['variantBundleRate']} | "
            f"{row['controlMaxSelectedBundleSize']}/{row['variantMaxSelectedBundleSize']} | {row['blockers']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build focused GreedRL phase gate from ablation artifacts.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    report = build_report(Path(args.input_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "greedrl_phase_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "greedrl_phase_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[GREEDRL PHASE GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

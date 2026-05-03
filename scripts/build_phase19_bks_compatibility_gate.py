from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(candidate_dir: Path) -> dict[str, Any]:
    audit = read_json(candidate_dir / "phase19_bks_compatibility_audit.json")
    blockers: list[str] = []
    fingerprint = audit.get("instanceFingerprint", {})
    distance_rows = audit.get("distanceSemantics", [])
    checker_rows = audit.get("checkerSemantics", [])
    if not fingerprint:
        blockers.append("phase19-missing-instance-fingerprint")
    if not distance_rows:
        blockers.append("phase19-missing-distance-semantics")
    if not checker_rows:
        blockers.append("phase19-missing-checker-semantics")
    incumbent = audit.get("incumbentChecked", {})
    if not incumbent.get("feasible"):
        blockers.append("phase19-incumbent-not-feasible")
    if not audit.get("compatibilityConclusion"):
        blockers.append("phase19-missing-conclusion")
    reference_available = bool(audit.get("referenceRouteAvailable"))
    reference_checked = audit.get("referenceRouteChecked")
    reference_feasible = bool(reference_checked and reference_checked.get("feasible"))
    if reference_available and reference_checked is None:
        blockers.append("phase19-reference-not-checked")
    conclusion = str(audit.get("compatibilityConclusion", ""))
    if blockers:
        verdict = "FAIL"
    elif reference_available and reference_feasible and conclusion == "reference-route-feasible-model-compatible":
        verdict = "PASS"
    else:
        verdict = "PASS_WITH_LIMITS"
    return {
        "schemaVersion": "phase19-bks-compatibility-gate/v1",
        "candidateDir": str(candidate_dir),
        "instance": audit.get("instance"),
        "bks": fingerprint.get("bestKnown"),
        "incumbentVehicleCount": incumbent.get("vehicleCount"),
        "incumbentDistance": incumbent.get("totalDistance"),
        "distanceModeCount": len(distance_rows),
        "checkerModeCount": len(checker_rows),
        "referenceRouteAvailable": reference_available,
        "referenceRouteFeasible": reference_feasible,
        "compatibilityConclusion": conclusion,
        "recommendedNextStep": audit.get("recommendedNextStep"),
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 19 BKS Compatibility Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- instance: `{report['instance']}`",
        f"- BKS: `{report['bks']}`",
        f"- incumbent vehicles/distance: `{report['incumbentVehicleCount']}/{report['incumbentDistance']}`",
        f"- distance/checker modes: `{report['distanceModeCount']}/{report['checkerModeCount']}`",
        f"- reference route available/feasible: `{report['referenceRouteAvailable']}/{report['referenceRouteFeasible']}`",
        f"- conclusion: `{report['compatibilityConclusion']}`",
        f"- next step: `{report['recommendedNextStep']}`",
        f"- blockers: `{report['blockers']}`",
        "",
    ])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 19 BKS compatibility gate.")
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    report = build_report(Path(args.candidate_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase19_bks_compatibility_gate.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase19_bks_compatibility_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE19 BKS COMPATIBILITY GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

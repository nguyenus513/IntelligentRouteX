from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_gate(report_dir: Path) -> dict[str, Any]:
    report = read_json(report_dir / "phase22_final_benchmark_report.json")
    decision = report.get("decision", {})
    summary = report.get("summary", {})
    return {
        "schemaVersion": "phase22-release-gate/v1",
        "reportDir": str(report_dir),
        "verdict": decision.get("verdict"),
        "claim": decision.get("claim"),
        "blockers": decision.get("blockers", []),
        "warnings": decision.get("warnings", []),
        "mediumWins": summary.get("mediumWins"),
        "mediumTies": summary.get("mediumTies"),
        "mediumLosses": summary.get("mediumLosses"),
        "mediumRuntimeP95Ms": summary.get("mediumRuntimeP95Ms"),
        "mediumHardViolations": summary.get("mediumHardViolations"),
        "rc101GapAfterPhase20": summary.get("rc101GapAfterPhase20"),
        "rc101GapAfterPhase23": summary.get("rc101GapAfterPhase23"),
        "rc101ReferenceFeasiblePhase23": summary.get("rc101ReferenceFeasiblePhase23"),
        "pass": decision.get("verdict") in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(gate: dict[str, Any]) -> str:
    return "\n".join([
        "# Phase 22 Release Gate",
        "",
        f"- verdict: `{gate['verdict']}`",
        f"- claim: `{gate['claim']}`",
        f"- blockers: `{gate['blockers']}`",
        f"- warnings: `{gate['warnings']}`",
        f"- medium wins/ties/losses: `{gate['mediumWins']}/{gate['mediumTies']}/{gate['mediumLosses']}`",
        f"- medium runtime p95 ms: `{gate['mediumRuntimeP95Ms']}`",
        f"- medium hard violations: `{gate['mediumHardViolations']}`",
        f"- RC101 gap after Phase 20/23: `{gate['rc101GapAfterPhase20']}/{gate['rc101GapAfterPhase23']}`",
        f"- RC101 reference feasible Phase 23: `{gate['rc101ReferenceFeasiblePhase23']}`",
        "",
    ])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 22 release gate.")
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    gate = build_gate(Path(args.report_dir))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase22_release_gate.json").write_text(json.dumps(gate, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "phase22_release_gate.md").write_text(markdown(gate), encoding="utf-8")
    print(f"[PHASE22 RELEASE GATE] wrote {output_dir}")
    return 0 if gate["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from build_phase15_large_benchmark_report import build_report as build_phase15_report
from build_phase15_large_benchmark_gate import build_report as build_phase15_gate


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_report(candidate_dir: Path, output_dir: Path, max_runtime_p95_ms: int) -> dict[str, Any]:
    phase16 = read_json(candidate_dir / "phase16_gap_reduction_results.json")
    aggregate = build_phase15_report(candidate_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "phase15_large_benchmark_report.json", aggregate)
    phase15_gate = build_phase15_gate(output_dir, max_runtime_p95_ms, 0.0)
    blockers = list(phase15_gate.get("blockers", []))
    budget_rows = phase16.get("budgetRows", [])
    if not budget_rows:
        blockers.append("phase16-missing-budget-evidence")
    for row in budget_rows:
        budget = row.get("budgetPolicy", {}) if isinstance(row.get("budgetPolicy"), dict) else {}
        if int(phase16.get("timeLimitMs") or 0) <= 5_000:
            if budget.get("mode") != "short-budget-parity":
                blockers.append("phase16-short-budget-mode-not-active")
            if int(budget.get("constructionMs") or 0) < int(phase16.get("timeLimitMs") or 0):
                blockers.append("phase16-short-budget-construction-starved")
            if int(budget.get("consolidationMs") or 0) != 0:
                blockers.append("phase16-short-budget-consolidation-not-disabled")
    verdict = "PASS" if not blockers and int(phase15_gate.get("wins") or 0) > 0 else "PASS_WITH_LIMITS" if not blockers else "FAIL"
    return {
        "schemaVersion": "phase16-gap-reduction-gate/v1",
        "candidateDir": str(candidate_dir),
        "timeLimitMs": phase16.get("timeLimitMs"),
        "phase15GateVerdict": phase15_gate.get("verdict"),
        "wins": phase15_gate.get("wins"),
        "ties": phase15_gate.get("ties"),
        "losses": phase15_gate.get("losses"),
        "ourSummary": phase15_gate.get("ourSummary"),
        "budgetRows": budget_rows,
        "blockers": blockers,
        "verdict": verdict,
        "pass": verdict in {"PASS", "PASS_WITH_LIMITS"},
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 16 Gap Reduction Gate",
        "",
        f"- verdict: `{report['verdict']}`",
        f"- phase15 gate: `{report['phase15GateVerdict']}`",
        f"- wins/ties/losses: `{report['wins']}/{report['ties']}/{report['losses']}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Instance | Vehicles | Runtime | Budget Mode | Construction | Consolidation |",
        "|---|---|---:|---:|---|---:|---:|",
    ]
    for row in report["budgetRows"]:
        budget = row.get("budgetPolicy", {})
        lines.append(
            f"| {row.get('suite')} | {row.get('instance')} | {row.get('vehicleCount')} | {row.get('runtimeMs')} | "
            f"{budget.get('mode')} | {budget.get('constructionMs')} | {budget.get('consolidationMs')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Phase 16 gap-reduction gate.")
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-runtime-p95-ms", type=int, default=15_000)
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    report = build_report(Path(args.candidate_dir), output_dir, args.max_runtime_p95_ms)
    write_json(output_dir / "phase16_gap_reduction_gate.json", report)
    (output_dir / "phase16_gap_reduction_gate.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE16 GAP REDUCTION GATE] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

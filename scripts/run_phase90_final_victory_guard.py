from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from run_phase55_promotion_guard import write_json
from run_phase84_antihardcode_guard import scan as antihardcode_scan


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "artifacts" / "benchmark" / "phase90_final_quality_v1" / "phase90_summary.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "benchmark" / "phase90_final_quality_v1" / "promotion_guard.json"


def evaluate_gate(summary: Dict[str, Any], anti_gate: str = "PASS", regressions: int = 0, summary_exists: bool = True) -> str:
    if not summary_exists or int(summary.get("timeoutCount", 0) or 0):
        return "FAIL"
    if bool(summary.get("requiresAcceptanceMissing")):
        return "FAIL"
    if int(summary.get("hardViolations", 0) or 0) or int(summary.get("overBudget", 0) or 0) or anti_gate != "PASS" or regressions:
        return "FAIL"
    if int(summary.get("acceptedCandidates", 0) or 0) > 0 and int(summary.get("objectiveImprovingCandidates", 0) or 0) > 0 and int(summary.get("qualityOpportunityWithoutImprovement", 0) or 0) == 0:
        return "PASS_STRONG"
    if bool(summary.get("boundedSearchNoImprovement")):
        return "PASS_WITH_LIMITS"
    if int(summary.get("acceptedCandidates", 0) or 0) > 0 or int(summary.get("checkerFeasibleCandidates", 0) or 0) > 0:
        return "PASS"
    return "PASS_WITH_LIMITS"


def run(input_path: Path, output_path: Path) -> Dict[str, Any]:
    summary_exists = input_path.exists()
    summary = json.loads(input_path.read_text(encoding="utf-8")) if summary_exists else {}
    anti = antihardcode_scan()
    gate = evaluate_gate(summary, str(anti.get("gate")), summary_exists=summary_exists)
    report = {"schemaVersion": "phase90-final-victory-guard/v1", "gate": gate, "antiHardcodeGate": anti.get("gate"), "productionMainReady": False, "summaryGate": summary.get("gate")}
    write_json(output_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 90 final victory guard.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = run(Path(args.input), Path(args.output))
    print(f"[PHASE90 VICTORY GUARD] {report['gate']} wrote {args.output}")
    return 0 if report.get("gate") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

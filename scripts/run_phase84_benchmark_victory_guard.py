from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from run_phase55_promotion_guard import write_json


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "artifacts" / "benchmark" / "phase84_unified_optimizer_v1" / "phase84_summary.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "benchmark" / "phase84_unified_optimizer_v1" / "promotion_guard.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(summary: Dict[str, Any]) -> Dict[str, Any]:
    hard = int(summary.get("aggregate", {}).get("hardViolations", 0) or 0)
    over_budget = int(summary.get("aggregate", {}).get("overBudget", 0) or 0)
    fallback = int(summary.get("aggregate", {}).get("fallback", 0) or 0)
    vroom_wins = int(summary.get("aggregate", {}).get("vroomWins", 0) or 0)
    anti = summary.get("antiHardcodeGate", "UNKNOWN")
    reasons = []
    if hard:
        reasons.append("hard-violation-regression")
    if over_budget:
        reasons.append("over-budget-regression")
    if fallback:
        reasons.append("fallback-regression")
    if anti != "PASS":
        reasons.append("anti-hardcode-fail")
    if reasons:
        gate = "FAIL"
    elif vroom_wins == 0:
        gate = "PASS_STRONG"
    else:
        gate = "PASS_WITH_LIMITS"
    return {"schemaVersion": "phase84-benchmark-victory-guard/v1", "gate": gate, "reasons": reasons, "vroomWins": vroom_wins}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 84 benchmark victory guard.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = evaluate(read_json(Path(args.input)))
    write_json(Path(args.output), report)
    print(f"[PHASE84 VICTORY GUARD] {report['gate']} wrote {args.output}")
    return 0 if report["gate"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

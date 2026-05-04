from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from run_phase67b_vroom_time_window_audit import run as run_tw_audit


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "artifacts" / "final" / "vroom_capability_full_v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def classify_row(row: Dict[str, Any]) -> str:
    if not row.get("supportedMapping", True) or not row.get("importValid", True):
        return "import-mapping-mismatch"
    if row.get("classification") in {"tie", "vroom-win", "challenger-win"} and row.get("vroomFeasibleByInternalChecker"):
        return "both-feasible"
    if row.get("classification") == "vroom-hard-fail":
        violations = row.get("champion", {}).get("violations", [])
        if "time-window-violation" in violations:
            return "true-vroom-time-window-violation"
        return "vroom-hard-fail"
    if row.get("classification") == "vroom-timeout":
        return "vroom-timeout"
    if row.get("timeUnitDiagnostics", {}).get("suspiciousScaleMismatch"):
        return "matrix-duration-mismatch"
    return "unknown"


def run(input_dir: Path, output_dir: Path) -> Dict[str, Any]:
    rows = read_json(input_dir / "vroom_comparator" / "per_instance_comparison.json")
    audited = [{"instance": row.get("instance"), "semanticClassification": classify_row(row), "sourceClassification": row.get("classification")} for row in rows]
    counts: Dict[str, int] = {}
    for row in audited:
        counts[row["semanticClassification"]] = counts.get(row["semanticClassification"], 0) + 1
    summary = {"schemaVersion": "phase76-vroom-semantic-audit/v1", "inputDir": str(input_dir), "classificationCounts": counts, "rows": audited, "gate": "PASS" if counts.get("unknown", 0) == 0 else "FAIL"}
    write_json(output_dir / "semantic_audit.json", summary)
    (output_dir / "semantic_audit.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def markdown(summary: Dict[str, Any]) -> str:
    lines = ["# Phase 76 VROOM Semantic Audit", "", f"Gate: **{summary['gate']}**", "", f"Counts: `{json.dumps(summary['classificationCounts'], sort_keys=True)}`", "", "| Instance | Semantic | Source |", "|---|---|---|"]
    for row in summary.get("rows", []):
        lines.append(f"| {row['instance']} | {row['semanticClassification']} | {row['sourceClassification']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run VROOM semantic audit on Phase 63 comparator artifacts.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default="artifacts/benchmark/phase76_vroom_capability_v1")
    args = parser.parse_args()
    summary = run(Path(args.input_dir), Path(args.output_dir))
    print(f"[PHASE76 VROOM SEMANTIC AUDIT] wrote {args.output_dir}")
    return 0 if summary["gate"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

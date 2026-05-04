from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "phase73_ablation_study_v1"
DEFAULT_DOC = REPO_ROOT / "docs" / "benchmark" / "ablation_study.md"


CONFIGS = [
    {"config": "base-incumbent-only", "qualityEffect": "baseline feasible construction", "runtimeRisk": "low", "stabilityEffect": "medium"},
    {"config": "+ internal solver generator", "qualityEffect": "candidate diversity and objective improvement", "runtimeRisk": "medium", "stabilityEffect": "requires deterministic candidate selection"},
    {"config": "+ route-pool", "qualityEffect": "vehicle/distance improvements when budget permits", "runtimeRisk": "high without hard cap", "stabilityEffect": "requires route-pool reserve and replay"},
    {"config": "+ stable replay", "qualityEffect": "no direct quality gain", "runtimeRisk": "low", "stabilityEffect": "high"},
    {"config": "+ hard budget guard", "qualityEffect": "may skip expensive improvements", "runtimeRisk": "low", "stabilityEffect": "high"},
    {"config": "+ synthetic integration", "qualityEffect": "food-like feasibility evidence", "runtimeRisk": "medium", "stabilityEffect": "dataset-dependent"},
]


def build_ablation() -> Dict[str, Any]:
    return {"schemaVersion": "phase73-ablation-study/v1", "configs": CONFIGS, "currentConclusion": "Phase 56F stability comes from stable replay plus hard budget guard; route-pool can improve quality but is a runtime-risk component without caps."}


def markdown(payload: Dict[str, Any]) -> str:
    lines = ["# Phase 73 Ablation Study", "", "| Config | Quality Effect | Runtime Risk | Stability Effect |", "|---|---|---|---|"]
    for row in payload["configs"]:
        lines.append(f"| {row['config']} | {row['qualityEffect']} | {row['runtimeRisk']} | {row['stabilityEffect']} |")
    lines.extend(["", f"Conclusion: {payload['currentConclusion']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Write Phase 73 ablation study summary.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--doc", default=str(DEFAULT_DOC))
    args = parser.parse_args()
    payload = build_ablation()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase73_ablation_study.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    text = markdown(payload)
    (output_dir / "phase73_ablation_study.md").write_text(text, encoding="utf-8")
    doc = Path(args.doc)
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(text, encoding="utf-8")
    print(f"[PHASE73 ABLATION] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

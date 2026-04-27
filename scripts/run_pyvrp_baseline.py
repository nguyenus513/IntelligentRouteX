from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, Sequence

from parse_solomon_vrptw import parse_solomon
from run_dispatch_benchmark_certification_suite import HOMBERGER_BEST_KNOWN, REPO_ROOT


DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "pyvrp-baseline"
DEFAULT_INSTANCES = ("C1_10_1", "R1_10_1", "RC1_10_1")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_homberger(instance: str) -> Dict[str, Any]:
    path = REPO_ROOT / "benchmarks" / "external" / "official" / "homberger" / f"{instance}.txt"
    normalized = parse_solomon(path)
    normalized["benchmarkFamily"] = "homberger"
    if instance in HOMBERGER_BEST_KNOWN:
        normalized["bestKnown"] = HOMBERGER_BEST_KNOWN[instance]
    return normalized


def pyvrp_available() -> bool:
    return importlib.util.find_spec("pyvrp") is not None


def parse_duration_ms(value: str) -> int:
    text = value.strip().lower()
    if text.endswith("ms"):
        return int(float(text[:-2]))
    if text.endswith("s"):
        return int(float(text[:-1]) * 1000)
    if text.endswith("m"):
        return int(float(text[:-1]) * 60_000)
    if text.endswith("h"):
        return int(float(text[:-1]) * 3_600_000)
    return int(float(text) * 1000)


def run_instance(instance: str, time_limit_ms: int) -> Dict[str, Any]:
    normalized = load_homberger(instance)
    best = normalized.get("bestKnown", {})
    if not pyvrp_available():
        return {
            "instance": instance,
            "solver": "pyvrp-hgs",
            "feasible": False,
            "runtimeMs": 0,
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["pyvrp-package-not-installed"],
            "bksVehicleCount": best.get("vehicleCount"),
            "bksDistance": best.get("objective"),
            "requestedTimeLimitMs": time_limit_ms,
        }
    return {
        "instance": instance,
        "solver": "pyvrp-hgs",
        "feasible": False,
        "runtimeMs": 0,
        "verdict": "EVIDENCE_GAP",
        "verdictReasons": ["pyvrp-adapter-parser-pending"],
        "bksVehicleCount": best.get("vehicleCount"),
        "bksDistance": best.get("objective"),
        "requestedTimeLimitMs": time_limit_ms,
    }


def markdown(rows: Sequence[Dict[str, Any]]) -> str:
    final = "PASS" if rows and all(row["verdict"] == "PASS" for row in rows) else "EVIDENCE_GAP"
    lines = ["# PyVRP/HGS Baseline", "", f"FINAL_VERDICT = {final}", ""]
    lines.append("| Instance | Feasible | Vehicles | BKS Vehicles | Distance | BKS Distance | Verdict | Reasons |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |")
    for row in rows:
        lines.append(
            f"| {row['instance']} | {row.get('feasible')} | {row.get('vehicleCount', 'n/a')} | {row.get('bksVehicleCount')} | {row.get('totalDistance', 'n/a')} | {row.get('bksDistance')} | {row['verdict']} | {', '.join(row.get('verdictReasons', []))} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PyVRP/HGS baseline if the optional pyvrp package is installed.")
    parser.add_argument("--instances", default=",".join(DEFAULT_INSTANCES))
    parser.add_argument("--time-limit", default="30m")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    instances = [part.strip() for part in args.instances.split(",") if part.strip()]
    rows = [run_instance(instance, parse_duration_ms(args.time_limit)) for instance in instances]
    output_root = Path(args.output_root)
    result = {"schemaVersion": "pyvrp-baseline/v1", "pyvrpInstalled": pyvrp_available(), "results": rows}
    write_json(output_root / "pyvrp_results.json", result)
    (output_root / "pyvrp_report.md").write_text(markdown(rows), encoding="utf-8")
    print(f"[PYVRP BASELINE JSON] {output_root / 'pyvrp_results.json'}")
    print(f"[PYVRP BASELINE REPORT] {output_root / 'pyvrp_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
